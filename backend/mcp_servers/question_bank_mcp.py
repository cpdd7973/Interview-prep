"""
Question Bank MCP Server
Manages interview questions and semantic search capabilities.
"""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import logging
import json
import os
import chromadb

from database import SessionLocal, Question, QuestionDifficulty, QuestionType
from sqlalchemy.sql.expression import func

logger = logging.getLogger(__name__)

# Tool Input Schemas (Pydantic models)
class GetQuestionsInput(BaseModel):
    role: str = Field(..., description="Job role to get questions for")
    difficulty: Optional[QuestionDifficulty] = Field(None, description="Filter by difficulty")
    limit: int = Field(10, description="Max number of questions to return")

class QuestionDataSchema(BaseModel):
    topic: str
    difficulty: QuestionDifficulty
    type: QuestionType
    question_text: str
    ideal_answer: Optional[str] = None
    tags: List[str] = []

class AddQuestionInput(BaseModel):
    role: str = Field(..., description="Job role")
    question_data: QuestionDataSchema = Field(..., description="Question details")

class EditQuestionInput(BaseModel):
    question_id: int = Field(..., description="ID of the question to edit")
    updates: Dict[str, Any] = Field(..., description="Dictionary of fields to update")

class DeleteQuestionInput(BaseModel):
    question_id: int = Field(..., description="ID of question to delete")

class BulkImportInput(BaseModel):
    json_file_path: str = Field(..., description="Path to the JSON file with questions")

class SemanticSearchInput(BaseModel):
    query: str = Field(..., description="The context or answer to search related questions for")
    role: str = Field(..., description="Job role to scope the search")
    top_k: int = Field(5, description="Number of results to return")

class QuestionBankServer:
    """
    Question Bank MCP Server providing complete CRUD and semantic search functionality.
    """
    def __init__(self):
        self.name = "question-bank-mcp"
        self.version = "1.0.0"
        self.tools = {
            "get_questions_by_role": self.get_questions_by_role,
            "add_question": self.add_question,
            "edit_question": self.edit_question,
            "delete_question": self.delete_question,
            "bulk_import_questions": self.bulk_import_questions,
            "semantic_search": self.semantic_search
        }
        
        # Lazy-loaded Vector DB
        self._chroma_client = None
        self._initialized = False

    @property
    def chroma_client(self):
        """Lazy initialization of ChromaDB client."""
        if self._chroma_client is None:
            logger.info("Initializing ChromaDB client...")
            self._chroma_client = chromadb.Client()
        return self._chroma_client

    def initialize(self):
        """Explicitly load data. Should be called in a background task to prevent blocking startup."""
        if self._initialized:
            return
        logger.info("Starting background synchronization of Question Bank to ChromaDB...")
        self._load_initial_data()
        self._initialized = True

    def _get_collection(self, role: str):
        collection_name = f"{role}_questions".replace("-", "_").replace(" ", "_").lower()
        return self.chroma_client.get_or_create_collection(name=collection_name)

    def _sync_question_to_chroma(self, question: Question):
        """Sync a single SQLite Question to ChromaDB."""
        collection = self._get_collection(question.role)
        # ChromaDB requires string IDs
        # Store the question in documents for semantic similarity, and answer in metadata for retrieval payload
        answer_text = question.ideal_answer if question.ideal_answer else "No specific answer provided."
        
        collection.upsert(
            documents=[question.question_text],
            metadatas=[{
                "topic": question.topic,
                "difficulty": question.difficulty.value,
                "type": question.type.value,
                "tags": ",".join(question.tags) if question.tags else "",
                "ideal_answer": answer_text[:4000] # Limiting size for Chroma metadata constraints
            }],
            ids=[str(question.id)]
        )

    def _load_initial_data(self):
        """Load from JSON files into SQLite and ChromaDB on startup if DB is empty."""
        db: Session = SessionLocal()
        try:
            # Check if we have any questions
            count = db.query(Question).count()
            if count > 0:
                # Still need to sync existing questions into in-memory ChromaDB
                questions = db.query(Question).all()
                for q in questions:
                    self._sync_question_to_chroma(q)
                logger.info(f"Loaded {len(questions)} questions into ChromaDB from SQLite")
                return

            logger.info("Initializing Question Bank from JSON files...")
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            q_bank_dir = os.path.join(base_dir, "question_bank")
            
            if not os.path.exists(q_bank_dir):
                return
                
            for filename in os.listdir(q_bank_dir):
                if filename.endswith(".json"):
                    file_path = os.path.join(q_bank_dir, filename)
                    self.bulk_import_questions(BulkImportInput(json_file_path=file_path))
                    
            logger.info("Question Bank initialization complete.")
        except Exception as e:
            logger.error(f"Error loading initial questions: {e}")
        finally:
            db.close()

    def get_questions_by_role(self, input_data: GetQuestionsInput) -> Dict[str, Any]:
        db: Session = SessionLocal()
        try:
            query = db.query(Question).filter(Question.role == input_data.role)
            if input_data.difficulty:
                query = query.filter(Question.difficulty == input_data.difficulty)
                
            questions = query.order_by(func.random()).limit(input_data.limit).all()
            
            # Fallback to software_engineer if role brings back zero questions
            if not questions and input_data.role.strip().lower() != "software_engineer":
                logger.warning(f"No questions found for role '{input_data.role}'. Falling back to 'software_engineer'.")
                fallback_query = db.query(Question).filter(Question.role == "software_engineer")
                if input_data.difficulty:
                    fallback_query = fallback_query.filter(Question.difficulty == input_data.difficulty)
                questions = fallback_query.order_by(func.random()).limit(input_data.limit).all()
            
            results = []
            for q in questions:
                results.append({
                    "id": q.id,
                    "topic": q.topic,
                    "difficulty": q.difficulty.value,
                    "type": q.type.value,
                    "question_text": q.question_text,
                    "ideal_answer": q.ideal_answer,
                    "tags": q.tags
                })
                
            return {
                "success": True,
                "role": input_data.role,
                "questions": results,
                "count": len(results)
            }
        except Exception as e:
            logger.error(f"Error getting questions: {e}")
            return {"success": False, "error": str(e)}
        finally:
            db.close()

    def add_question(self, input_data: AddQuestionInput) -> Dict[str, Any]:
        db: Session = SessionLocal()
        try:
            data = input_data.question_data
            question = Question(
                role=input_data.role,
                topic=data.topic,
                difficulty=data.difficulty,
                type=data.type,
                question_text=data.question_text,
                ideal_answer=data.ideal_answer,
                tags=data.tags
            )
            
            db.add(question)
            db.commit()
            db.refresh(question)
            
            self._sync_question_to_chroma(question)
            
            return {
                "success": True,
                "question_id": question.id,
                "message": "Question added successfully"
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Error adding question: {e}")
            return {"success": False, "error": str(e)}
        finally:
            db.close()

    def edit_question(self, input_data: EditQuestionInput) -> Dict[str, Any]:
        db: Session = SessionLocal()
        try:
            question = db.query(Question).filter(Question.id == input_data.question_id).first()
            if not question:
                return {"success": False, "error": "Question not found"}
                
            for key, value in input_data.updates.items():
                if hasattr(question, key):
                    setattr(question, key, value)
                    
            db.commit()
            db.refresh(question)
            
            self._sync_question_to_chroma(question)
            
            return {
                "success": True,
                "question_id": question.id,
                "message": "Question updated successfully"
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Error editing question: {e}")
            return {"success": False, "error": str(e)}
        finally:
            db.close()

    def delete_question(self, input_data: DeleteQuestionInput) -> Dict[str, Any]:
        db: Session = SessionLocal()
        try:
            question = db.query(Question).filter(Question.id == input_data.question_id).first()
            if not question:
                return {"success": False, "error": "Question not found"}
                
            role = question.role
            qid = str(question.id)
            
            db.delete(question)
            db.commit()
            
            # Remove from ChromaDB
            collection = self._get_collection(role)
            collection.delete(ids=[qid])
            
            return {
                "success": True,
                "message": "Question deleted successfully"
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting question: {e}")
            return {"success": False, "error": str(e)}
        finally:
            db.close()

    def bulk_import_questions(self, input_data: BulkImportInput) -> Dict[str, Any]:
        db: Session = SessionLocal()
        try:
            with open(input_data.json_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            role = data.get("role")
            if not role:
                return {"success": False, "error": "JSON missing 'role' key"}
                
            questions_list = data.get("questions", [])
            imported_count = 0
            
            for q_data in questions_list:
                question = Question(
                    role=role,
                    topic=q_data.get("topic", "General"),
                    difficulty=QuestionDifficulty(q_data.get("difficulty", "MEDIUM")),
                    type=QuestionType(q_data.get("type", "TECHNICAL")),
                    question_text=q_data.get("question_text", ""),
                    ideal_answer=q_data.get("ideal_answer"),
                    tags=q_data.get("tags", [])
                )
                db.add(question)
                db.commit()
                db.refresh(question)
                self._sync_question_to_chroma(question)
                imported_count += 1
                
            return {
                "success": True,
                "imported_count": imported_count,
                "role": role
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Error bulk importing questions: {e}")
            return {"success": False, "error": str(e)}
        finally:
            db.close()

    def semantic_search(self, input_data: SemanticSearchInput) -> Dict[str, Any]:
        try:
            collection = self._get_collection(input_data.role)
            
            # Check if collection is empty
            if collection.count() == 0:
                return {"success": True, "results": [], "info": "Collection is empty"}
                
            results = collection.query(
                query_texts=[input_data.query],
                n_results=min(input_data.top_k, collection.count())
            )
            
            search_results = []
            if results["ids"] and len(results["ids"]) > 0:
                for idx, qid in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][idx] if results["metadatas"] else {}
                    ideal_answer = metadata.pop("ideal_answer", None)
                    
                    search_results.append({
                        "question_id": int(qid),
                        "question_text": results["documents"][0][idx],
                        "ideal_answer": ideal_answer,
                        "metadata": metadata,
                        "distance": results["distances"][0][idx] if results["distances"] else None
                    })
                    
            return {
                "success": True,
                "results": search_results
            }
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return {"success": False, "error": str(e)}

# Singleton instance
question_bank_mcp = QuestionBankServer()
