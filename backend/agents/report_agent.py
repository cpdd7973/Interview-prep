"""
Report Agent Node
Consumes the evaluation results to generate a final PDF report and email it
to the system administrator.
"""
from typing import Dict, Any
import logging
import os

from agents.state import InterviewState
from config import settings
from mcp_servers.report_mcp import report_mcp, CompileReportInput, ExportPdfInput, EmailReportInput

logger = logging.getLogger(__name__)

def report_node(state: InterviewState) -> Dict[str, Any]:
    """
    LangGraph node for generating and emailing the interview report.
    """
    logger.info(f"📄 Report Agent generating final document for candidate in session")
    
    if state.get("status") != "EVALUATED" or not state.get("evaluation"):
        logger.info("Session not EVALUATED. Skipping report generation.")
        return state
        
    try:
        # 1. Compile Report Data
        session_data = {
            "candidate_name": state.get("candidate_name"),
            "candidate_email": state.get("candidate_email"),
            "job_role": state.get("job_role"),
            "company": state.get("company"),
            "scheduled_at": state.get("scheduled_at"),
            "interviewer_designation": state.get("interviewer_designation")
        }
        
        compile_resp = report_mcp.compile_report(CompileReportInput(
            session_data=session_data,
            evaluation_data=state["evaluation"]
        ))
        
        if not compile_resp.get("success"):
            raise ValueError(f"Failed to compile report: {compile_resp.get('error')}")
            
        report_data = compile_resp["report_data"]
        
        # 2. Export PDF
        room_id = state.get("room_id", "unknown_room")
        pdf_path = os.path.join(settings.REPORTS_DIR, f"{room_id}_report.pdf")
        
        export_resp = report_mcp.export_pdf(ExportPdfInput(
            report_data=report_data,
            output_path=str(pdf_path)
        ))
        
        if not export_resp.get("success"):
            raise ValueError(f"Failed to export PDF: {export_resp.get('error')}")
            
        logger.info(f"✅ Generated PDF report at {pdf_path}")
        
        # 3. Email Admin
        admin_email = settings.admin_email
        email_resp = report_mcp.email_report_to_admin(EmailReportInput(
            report_path=str(pdf_path),
            room_id=room_id,
            admin_email=admin_email
        ))
        
        if not email_resp.get("success"):
            logger.error(f"Failed to email admin: {email_resp.get('error')}")
        else:
            logger.info(f"✅ Emailed report notice to {admin_email}")
            
        return dict(state, status="REPORTED")
        
    except Exception as e:
        logger.error(f"❌ Report agent failed: {e}")
        return dict(state, error=f"Report failed: {str(e)}")
