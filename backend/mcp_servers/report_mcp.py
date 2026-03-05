"""
Report MCP Server
Generates PDF reports and coordinates email delivery.
"""
from typing import Dict, Any
from pydantic import BaseModel, Field
import logging
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

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
        self.version = "1.0.0"
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

    def export_pdf(self, input_data: ExportPdfInput) -> Dict[str, Any]:
        try:
            doc = SimpleDocTemplate(input_data.output_path, pagesize=letter)
            styles = getSampleStyleSheet()
            elements = []
            
            report = input_data.report_data
            sess = report.get("session", {})
            eval_data = report.get("evaluation", {})
            
            # Title
            elements.append(Paragraph("Interview Report", styles['Title']))
            elements.append(Spacer(1, 20))
            
            # Session Summary
            elements.append(Paragraph(f"<b>Candidate:</b> {sess.get('candidate_name', 'Unknown')}", styles['Normal']))
            elements.append(Paragraph(f"<b>Role:</b> {sess.get('job_role', 'Unknown')}", styles['Normal']))
            elements.append(Paragraph(f"<b>Date:</b> {sess.get('scheduled_at', 'Unknown')}", styles['Normal']))
            elements.append(Spacer(1, 20))
            
            # Scores Table
            scores = eval_data # Evaluation data is flat, not nested under "scores"
            data = [
                ['Dimension', 'Score (0-10)'],
                ['Technical Knowledge', str(scores.get('technical_score', 'N/A'))],
                ['Communication Clarity', str(scores.get('communication_score', 'N/A'))],
                ['Problem Solving', str(scores.get('problem_solving_score', 'N/A'))],
                ['Behavioral Fit', str(scores.get('behavioral_score', 'N/A'))],
                ['Confidence & Completeness', str(scores.get('confidence_score', 'N/A'))],
                ['Overall Score', str(scores.get('overall_score', 'N/A'))]
            ]
            t = Table(data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0,0), (-1,0), 12),
                ('BACKGROUND', (0,1), (-1,-1), colors.beige),
                ('GRID', (0,0), (-1,-1), 1, colors.black)
            ]))
            elements.append(t)
            elements.append(Spacer(1, 20))
            
            # Qualitative Feedback
            elements.append(Paragraph("<b>Qualitative Feedback:</b>", styles['Heading2']))
            feedback_text = eval_data.get("feedback", "No feedback provided.")
            elements.append(Paragraph(feedback_text.replace('\n', '<br/>'), styles['Normal']))
            
            doc.build(elements)
            logger.info(f"Generated PDF to {input_data.output_path}")
            
            return {
                "success": True,
                "pdf_path": input_data.output_path
            }
        except Exception as e:
            logger.error(f"❌ Error generating PDF: {e}")
            return {"success": False, "error": str(e)}

    def email_report_to_admin(self, input_data: EmailReportInput) -> Dict[str, Any]:
        """Email report to admin (we'll just use the gmail_mcp tool directly or standard logic)"""
        try:
            if not os.path.exists(input_data.report_path):
                return {"success": False, "error": f"PDF not found at {input_data.report_path}"}
                
            subject = f"Interview Report: Room {input_data.room_id}"
            body_html = f"<p>Please find the interview report attached for room <b>{input_data.room_id}</b>.</p><p><i>- Interview Agent System</i></p>"
            
            # Typically you'd encode attachment into the email via Gmail API 
            # (which gmail_mcp.send_email doesn't overtly support attachments yet, so we'll 
            # notify the admin where the file exists locally, or enhance the email tool later.
            # Here, we will just email a notice with the file path since it's local)
            body_html += f"<p>File is located at server path: <code>{input_data.report_path}</code></p>"
            
            email_input = SendEmailInput(
                to_email=input_data.admin_email,
                subject=subject,
                body=body_html,
                is_html=True
            )
            
            resp = gmail_mcp.send_email(email_input)
            
            if resp.get("success"):
                return {
                    "success": True,
                    "message": "Report notification sent to admin"
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
