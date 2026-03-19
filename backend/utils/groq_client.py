"""
Groq API client wrapper with fallback to Gemini.
Handles LLM inference for all agents.
"""
import os
from typing import Optional, List, Dict
import logging
from config import settings

logger = logging.getLogger(__name__)

try:
    from langchain_groq import ChatGroq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("langchain-groq not installed")

import asyncio

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("langchain-google-genai not installed")

async def _init_gemini_client():
    if not GEMINI_AVAILABLE or not settings.gemini_api_key:
        return None
    return ChatGoogleGenerativeAI(
        google_api_key=settings.gemini_api_key,
        model="gemini-pro",
        temperature=0.7
    )

async def _lazy_init_gemini():
    try:
        return await asyncio.wait_for(_init_gemini_client(), timeout=2.0)
    except (asyncio.TimeoutError, Exception):
        logger.warning("Gemini unavailable, Groq-only mode active")
        return None


class LLMClient:
    """
    Unified LLM client with automatic fallback.
    Primary: Groq (fast, free tier)
    Fallback: Gemini (reliable, free tier)
    """
    
    def __init__(self, model: str = "llama-3.3-70b-versatile", temperature: float = 0.7):
        self.model = model
        self.temperature = temperature
        self.primary_llm = None
        self.fallback_llm = None
        
        # We check for keys but don't instantiate immediately to avoid import-time crashes
        if not GROQ_AVAILABLE:
            logger.warning("langchain-groq not installed. LLM will fail.")
        if not settings.groq_api_key:
            logger.warning("GROQ_API_KEY missing. LLM will fail.")
        
        self.initialized = False
        
    def _ensure_initialized(self):
        """Lazy initialization of the actual LLM objects."""
        if self.initialized:
            return

        if GROQ_AVAILABLE and settings.groq_api_key:
            try:
                self.primary_llm = ChatGroq(
                    groq_api_key=settings.groq_api_key,
                    model_name=self.model,
                    temperature=self.temperature
                )
                logger.info("✅ Groq LLM initialized lazily")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Groq: {e}")
        
        self.initialized = True
        
        # Initialize fallback LLM (Gemini) - DISABLED due to hang in this environment
        # if GEMINI_AVAILABLE and settings.gemini_api_key:
        #    try:
        #        print("DEBUG: Initializing ChatGoogleGenerativeAI...")
        #        self.fallback_llm = ChatGoogleGenerativeAI(
        #            google_api_key=settings.gemini_api_key,
        #            model="gemini-pro",
        #            temperature=temperature
        #        )
        #        logger.info("✅ Gemini LLM initialized as fallback")
        #    except Exception as e:
        #        logger.error(f"❌ Failed to initialize Gemini: {e}")
        
        if not self.primary_llm and not self.fallback_llm:
            # We don't raise error in __init__ anymore, we do it in get_llm
            pass
    
    def get_llm(self):
        """Get the active LLM instance (primary or fallback)."""
        self._ensure_initialized()
        llm = self.primary_llm if self.primary_llm else self.fallback_llm
        if not llm:
            raise RuntimeError("No LLM is available. Please check your GROQ_API_KEY in the .env file.")
        return llm
    
    async def invoke_async(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Async approach specifically meant to handle the fallback delay safely.
        """
        llm = self.get_llm()
        
        try:
            # We use the sync invoke since groq is fast enough, or run in executor
            response = await asyncio.to_thread(self.primary_llm.invoke, messages, **kwargs)
            return response.content
        except Exception as e:
            logger.error(f"❌ LLM invocation failed: {e}")
            
            logger.info("🔄 Attempting fallback LLM...")
            # Lazy init gemini only when we actually need the fallback
            if not self.fallback_llm:
                 self.fallback_llm = await _lazy_init_gemini()
                 
            if self.fallback_llm:
                try:
                    response = await asyncio.to_thread(self.fallback_llm.invoke, messages, **kwargs)
                    return response.content
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback LLM also failed: {fallback_error}")
            
            raise RuntimeError(f"All LLM attempts failed: {e}")
    
    def invoke(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Synchronous proxy for compatibility where `invoke` is used directly.
        (If you use fallback here, it will attempt a synchronous loop which might require event loop handling)
        """
        llm = self.primary_llm
        if not llm:
             raise RuntimeError("Primary LLM unavailable and sync invoke doesn't support lazy async fallback.")
             
        try:
            response = llm.invoke(messages, **kwargs)
            return response.content
        except Exception as e:
            logger.error(f"❌ Sync LLM invocation failed: {e}")
            raise RuntimeError(f"Sync LLM attempt failed: {e}")


# Global client instance
llm_client = LLMClient()
