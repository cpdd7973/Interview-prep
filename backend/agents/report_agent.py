"""
Report Agent Node
Consumes the evaluation results to generate a final PDF report and email it
to the system administrator.
"""
from typing import Dict, Any
import logging
import os

from agents.state import InterviewState
from config import settings, REPORTS_DIR
from mcp_servers.report_mcp import report_mcp, CompileReportInput, ExportPdfInput, EmailReportInput
from database import SessionLocal, Evaluation

logger = logging.getLogger(__name__)

# Reports directory is now imported from config.py

def report_node(state: InterviewState) -> Dict[str, Any]:
    """
    LangGraph node for generating and emailing the interview report.
    """
    logger.info(f"📄 Report Agent generating final document for {state.get('candidate_name')}")
    
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
        candidate_name = state.get("candidate_name", "unknown").replace(" ", "_")
        pdf_filename = f"{room_id}_{candidate_name}_report.pdf"
        pdf_path = os.path.join(REPORTS_DIR, pdf_filename)
        
        export_resp = report_mcp.export_pdf(ExportPdfInput(
            report_data=report_data,
            output_path=pdf_path
        ))
        
        if not export_resp.get("success"):
            raise ValueError(f"Failed to export PDF: {export_resp.get('error')}")
            
        logger.info(f"✅ Generated PDF report at {pdf_path}")
        
        # 3. Save report_path to Evaluation DB record
        db = SessionLocal()
        try:
            evaluation = db.query(Evaluation).filter(Evaluation.room_id == room_id).first()
            if evaluation:
                evaluation.report_path = pdf_path
                db.commit()
                logger.info(f"💾 Saved report_path to Evaluation record")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save report_path to DB: {e}")
        finally:
            db.close()
        
        # 4. Email Admin
        admin_email = settings.admin_email
        if admin_email:
            email_resp = report_mcp.email_report_to_admin(EmailReportInput(
                report_path=pdf_path,
                room_id=room_id,
                admin_email=admin_email
            ))
            
            if not email_resp.get("success"):
                logger.error(f"⚠️ Failed to email admin: {email_resp.get('error')}")
                logger.info("Report generated but email delivery failed. PDF saved locally.")
            else:
                logger.info(f"✅ Report emailed to {admin_email}")
        else:
            logger.warning("⚠️ No admin_email configured. Report saved locally only.")
            
        return {
            **state,
            "status": "REPORTED",
            "report_path": pdf_path
        }
        
    except Exception as e:
        logger.error(f"❌ Report agent failed: {e}", exc_info=True)
        return {**state, "error": f"Report failed: {str(e)}"}
