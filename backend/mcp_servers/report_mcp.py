"""
Report MCP Server
Generates professional PDF reports and coordinates email delivery.
"""
from typing import Dict, Any
from pydantic import BaseModel, Field
import logging
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from config import settings
from mcp_servers.gmail_mcp import gmail_mcp, SendEmailInput

logger = logging.getLogger(__name__)

# Input Schemas
class CompileReportInput(BaseModel):
    evaluation_data: Dict[str, Any] = Field(..., description="Scores and feedback")
    session_data: Dict[str, Any] = Field(..., description="Candidate and Session info")

class ExportPdfInput(BaseModel):
    report_data: Dict[str, Any] = Field(..., description="Compiled report data")
    output_path: str = Field(..., description="Destination PDF file path")

class EmailReportInput(BaseModel):
    report_path: str = Field(..., description="Path to generated PDF")
    room_id: str = Field(..., description="Session room ID")
    admin_email: str = Field(..., description="Admin email to receive the report")

class ReportMCPServer:
    def __init__(self):
        self.name = "report-mcp-server"
        self.version = "2.0.0"
        self.tools = {
            "compile_report": self.compile_report,
            "export_pdf": self.export_pdf,
            "email_report_to_admin": self.email_report_to_admin
        }

    def compile_report(self, input_data: CompileReportInput) -> Dict[str, Any]:
        try:
            report_data = {
                "generated_at": datetime.utcnow().isoformat(),
                "session": input_data.session_data,
                "evaluation": input_data.evaluation_data
            }
            return {
                "success": True,
                "report_data": report_data
            }
        except Exception as e:
            logger.error(f"❌ Error compiling report: {e}")
            return {"success": False, "error": str(e)}

    def _get_score_color(self, score: float) -> colors.Color:
        """Return color based on score threshold."""
        if score >= 8:
            return colors.HexColor("#22c55e")  # green
        elif score >= 6:
            return colors.HexColor("#3b82f6")  # blue
        elif score >= 4:
            return colors.HexColor("#f59e0b")  # amber
        else:
            return colors.HexColor("#ef4444")  # red

    def _get_verdict(self, overall: float) -> str:
        if overall >= 8:
            return "STRONG HIRE"
        elif overall >= 6:
            return "HIRE"
        elif overall >= 5:
            return "MAYBE"
        else:
            return "NO HIRE"

    def export_pdf(self, input_data: ExportPdfInput) -> Dict[str, Any]:
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(input_data.output_path), exist_ok=True)
            
            doc = SimpleDocTemplate(
                input_data.output_path,
                pagesize=letter,
                leftMargin=0.75*inch,
                rightMargin=0.75*inch,
                topMargin=0.75*inch,
                bottomMargin=0.75*inch
            )
            
            styles = getSampleStyleSheet()
            elements = []
            
            report = input_data.report_data
            sess = report.get("session", {})
            eval_data = report.get("evaluation", {})
            scores = eval_data.get("scores", eval_data)  # Handle both nested and flat
            feedback = eval_data.get("feedback", "No feedback provided.")
            
            # Custom Styles
            title_style = ParagraphStyle(
                'CustomTitle', parent=styles['Title'],
                fontSize=24, spaceAfter=6, textColor=colors.HexColor("#1e293b")
            )
            subtitle_style = ParagraphStyle(
                'CustomSubtitle', parent=styles['Normal'],
                fontSize=11, textColor=colors.HexColor("#64748b"), alignment=TA_CENTER
            )
            heading_style = ParagraphStyle(
                'CustomHeading', parent=styles['Heading2'],
                fontSize=14, textColor=colors.HexColor("#1e40af"),
                spaceBefore=16, spaceAfter=8
            )
            
            # === HEADER ===
            elements.append(Paragraph("Interview Evaluation Report", title_style))
            generated = report.get("generated_at", datetime.utcnow().isoformat())
            elements.append(Paragraph(f"Generated: {generated[:19].replace('T', ' ')} UTC", subtitle_style))
            elements.append(Spacer(1, 12))
            elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#3b82f6")))
            elements.append(Spacer(1, 16))
            
            # === CANDIDATE INFO ===
            elements.append(Paragraph("Candidate Information", heading_style))
            info_data = [
                ["Candidate", sess.get("candidate_name", "Unknown")],
                ["Email", sess.get("candidate_email", "N/A")],
                ["Position", sess.get("job_role", "Unknown")],
                ["Company", sess.get("company", "Unknown")],
                ["Interviewer", sess.get("interviewer_designation", "N/A")],
                ["Scheduled", str(sess.get("scheduled_at", "N/A"))],
            ]
            info_table = Table(info_data, colWidths=[1.8*inch, 4.5*inch])
            info_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#475569")),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(info_table)
            elements.append(Spacer(1, 16))
            
            # === SCORES TABLE ===
            elements.append(Paragraph("Evaluation Scores", heading_style))
            
            tech = float(scores.get("technical_score", 0))
            comm = float(scores.get("communication_score", 0))
            prob = float(scores.get("problem_solving_score", 0))
            behav = float(scores.get("behavioral_score", 0))
            conf = float(scores.get("confidence_score", 0))
            overall = float(scores.get("overall_score", 0))
            
            score_rows = [
                ["Dimension", "Score", "Rating"],
                ["Technical Knowledge (30%)", f"{tech:.1f} / 10", self._get_verdict_label(tech)],
                ["Communication Clarity (20%)", f"{comm:.1f} / 10", self._get_verdict_label(comm)],
                ["Problem Solving (25%)", f"{prob:.1f} / 10", self._get_verdict_label(prob)],
                ["Behavioral Fit (15%)", f"{behav:.1f} / 10", self._get_verdict_label(behav)],
                ["Confidence & Completeness (10%)", f"{conf:.1f} / 10", self._get_verdict_label(conf)],
            ]
            
            t = Table(score_rows, colWidths=[3.2*inch, 1.5*inch, 1.5*inch])
            
            # Color each score cell
            table_style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
            
            # Color-code rating cells
            all_scores = [tech, comm, prob, behav, conf]
            for i, s in enumerate(all_scores):
                table_style.append(('TEXTCOLOR', (2, i+1), (2, i+1), self._get_score_color(s)))
                table_style.append(('FONTNAME', (2, i+1), (2, i+1), 'Helvetica-Bold'))
            
            t.setStyle(TableStyle(table_style))
            elements.append(t)
            elements.append(Spacer(1, 12))
            
            # === OVERALL SCORE ===
            verdict = self._get_verdict(overall)
            verdict_color = self._get_score_color(overall)
            
            overall_data = [["OVERALL SCORE", f"{overall:.1f} / 10", verdict]]
            ot = Table(overall_data, colWidths=[3.2*inch, 1.5*inch, 1.5*inch])
            ot.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
                ('TEXTCOLOR', (2, 0), (2, 0), verdict_color),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 12),
            ]))
            elements.append(ot)
            elements.append(Spacer(1, 20))
            
            # === QUALITATIVE FEEDBACK ===
            elements.append(Paragraph("Qualitative Feedback", heading_style))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
            elements.append(Spacer(1, 8))
            
            feedback_style = ParagraphStyle(
                'Feedback', parent=styles['Normal'],
                fontSize=10, leading=14, textColor=colors.HexColor("#334155"),
                spaceBefore=4, spaceAfter=4
            )
            
            # Split feedback into paragraphs
            for para in feedback.split('\n'):
                para = para.strip()
                if para:
                    elements.append(Paragraph(para.replace('<', '&lt;').replace('>', '&gt;'), feedback_style))
                    elements.append(Spacer(1, 4))
            
            # === FOOTER ===
            elements.append(Spacer(1, 30))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1")))
            footer_style = ParagraphStyle(
                'Footer', parent=styles['Normal'],
                fontSize=8, textColor=colors.HexColor("#94a3b8"), alignment=TA_CENTER
            )
            elements.append(Spacer(1, 6))
            elements.append(Paragraph("Generated by Interview Agent System • Confidential", footer_style))
            
            doc.build(elements)
            logger.info(f"✅ Generated PDF report at {input_data.output_path}")
            
            return {
                "success": True,
                "pdf_path": input_data.output_path
            }
        except Exception as e:
            logger.error(f"❌ Error generating PDF: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _get_verdict_label(self, score: float) -> str:
        if score >= 8:
            return "Excellent"
        elif score >= 6:
            return "Good"
        elif score >= 4:
            return "Average"
        else:
            return "Poor"

    def email_report_to_admin(self, input_data: EmailReportInput) -> Dict[str, Any]:
        """Email report PDF to admin as attachment."""
        try:
            if not os.path.exists(input_data.report_path):
                return {"success": False, "error": f"PDF not found at {input_data.report_path}"}
            
            candidate_info = input_data.room_id  # Will be enriched by caller
            subject = f"📋 Interview Report: {input_data.room_id}"
            body_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px;">
                <h2 style="color: #1e40af;">Interview Report Ready</h2>
                <p>The interview evaluation for session <b>{input_data.room_id}</b> has been completed.</p>
                <p>Please find the detailed PDF report attached to this email.</p>
                <hr style="border: 1px solid #e2e8f0;">
                <p style="color: #64748b; font-size: 12px;">
                    <i>— Interview Agent System</i>
                </p>
            </div>
            """
            
            email_input = SendEmailInput(
                to_email=input_data.admin_email,
                subject=subject,
                body=body_html,
                is_html=True,
                attachment_path=input_data.report_path  # Attach the PDF!
            )
            
            resp = gmail_mcp.send_email(email_input)
            
            if resp.get("success"):
                logger.info(f"✅ Report emailed to {input_data.admin_email} via {resp.get('method', 'unknown')}")
                return {
                    "success": True,
                    "message": f"Report sent to {input_data.admin_email}"
                }
            else:
                return {
                    "success": False,
                    "error": resp.get("error", "Unknown email error")
                }
        except Exception as e:
            logger.error(f"❌ Error emailing admin: {e}")
            return {"success": False, "error": str(e)}

# Singleton instance
report_mcp = ReportMCPServer()
