import os
import re
import json
import torch
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from groq import Groq
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from app import db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AIService:
    """AI Service for email generation, summarization, reply suggestion, and classification.
    
    This service provides various AI-powered functionalities for email management,
    including content generation, sentiment analysis, and email classification.
    """

    def __init__(self):
        """Initialize the AI service with necessary models and clients."""
        # --- Groq Client ---
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "llama-3.3-70b-versatile"  # Recommended latest Groq Llama

        # --- Sentiment Analysis Model ---
        self.sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english"
        )

        # --- Classification Model ---
        self.classifier_tokenizer = None
        self.classifier_model = None
        self._load_classification_model()

    # -----------------------------
    # Load HuggingFace Classification Model
    # -----------------------------
    def _load_classification_model(self) -> None:
        """Load the classification model from HuggingFace."""
        try:
            model_name = "distilbert-base-uncased-finetuned-sst-2-english"
            self.classifier_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.classifier_model = AutoModelForSequenceClassification.from_pretrained(model_name)
            logger.info("Classification model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading classification model: {e}")
            raise RuntimeError(f"Failed to load classification model: {str(e)}")

    # -----------------------------
    # Extract User Context
    # -----------------------------
    def extract_user_context(self, user) -> Dict[str, Any]:
        """Extract relevant context from user data including recent emails and preferences.
        
        Args:
            user: The user object containing user information
            
        Returns:
            Dict containing user context including recent emails and preferences
        """
        context = {
            "username": getattr(user, "username", None),
            "recent_emails": [],
            "common_senders": [],
            "user_preferences": {}
        }

        try:
            # Import models inside the method to avoid circular imports
            from app.models.email import Email
            
            recent_emails = (Email.query.filter_by(user_id=user.id)
                             .order_by(Email.received_at.desc())  # Using received_at instead of date_received
                             .limit(10)
                             .all())

            for email in recent_emails:
                sender = email.sender or "Unknown"

                context["recent_emails"].append({
                    "id": email.id,
                    "sender": sender,
                    "subject": email.subject,
                    "snippet": getattr(email, "snippet", ""),
                    "received_at": email.received_at.isoformat() if email.received_at else None  # Using received_at
                })

                if sender not in context["common_senders"]:
                    context["common_senders"].append(sender)

            if hasattr(user, "preferences"):
                try:
                    context["user_preferences"] = json.loads(user.preferences)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse user preferences for user {user.id}")

        except Exception as e:
            logger.error(f"Error extracting user context: {e}")

        return context

    # -----------------------------
    # Groq Chat Completion (Unified)
    # -----------------------------
    def _chat(self, prompt: str, temperature: float = 0.4, max_tokens: int = 1200) -> str:
        """Send a chat completion request to Groq API.
        
        Args:
            prompt: The prompt to send to the model
            temperature: Controls randomness in the output (0.0 to 1.0)
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            The model's response as a string
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert email assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in chat completion: {e}")
            return f"AI Error: {str(e)}"

    # -----------------------------
    # Generate Email with User Context
    # -----------------------------
    def generate_email_with_context(self, purpose: str, tone: str, notes: str, 
                                   user=None) -> Dict[str, Any]:
        """Generate an email with user-specific context.
        
        Args:
            purpose: The purpose of the email
            tone: The desired tone (formal, casual, etc.)
            notes: Additional notes for email content
            user: User object for context extraction
            
        Returns:
            Dictionary containing email subject and body
        """
        try:
            context = ""
            if user:
                user_ctx = self.extract_user_context(user)
                if user_ctx["recent_emails"]:
                    context += "Recent emails:\n"
                    for e in user_ctx["recent_emails"][:3]:
                        context += f"- {e['subject']}\n"
                if user_ctx["common_senders"]:
                    context += "Common senders:\n"
                    for s in user_ctx["common_senders"][:3]:
                        context += f"- {s}\n"

            # Create a more specific prompt that asks for a single email in plain text
            prompt = f"""
Generate a single, professional email based on the following information:

Purpose: {purpose}
Tone: {tone}
Additional notes: {notes}

{context}

Instructions:
1. Create only ONE complete email with a clear subject line and body
2. Use the specified tone ({tone}) throughout the email
3. Make the email concise and focused on the stated purpose
4. Format your response as plain text, not JSON
5. Start with "Subject:" followed by the subject line
6. After the subject line, include a blank line and then the email body

Example format:
Subject: Meeting Request for Next Week

Hi [Name],

I hope this email finds you well. I would like to schedule a meeting...

Best regards,
[Your Name]
"""

            result = self._chat(prompt)
            
            # Parse the result to extract subject and body
            lines = result.split('\n')
            subject = ""
            body = ""
            
            # Find the subject line
            for i, line in enumerate(lines):
                if line.lower().startswith('subject:'):
                    subject = line.replace('Subject:', '').replace('subject:', '').strip()
                    # The rest of the lines after the subject line form the body
                    body = '\n'.join(lines[i+1:]).strip()
                    break
            
            # If we couldn't parse the subject, use a default
            if not subject:
                subject = f"Email regarding {purpose}"
                body = result.strip()
            
            return {"subject": subject, "body": body}

        except Exception as e:
            logger.error(f"Error generating email with context: {e}")
            return {"subject": "Error", "body": str(e)}

    # -----------------------------
    # Generate Simple Email
    # -----------------------------
    def generate_email(self, purpose: str, tone: str, notes: str, 
                      additional_context: Optional[str] = None) -> Dict[str, Any]:
        """Generate a simple email based on provided parameters.
        
        Args:
            purpose: The purpose of the email
            tone: The desired tone (formal, casual, etc.)
            notes: Additional notes for email content
            additional_context: Optional additional context
            
        Returns:
            Dictionary containing email subject and body
        """
        try:
            ctx = f"\nAdditional context: {additional_context}" if additional_context else ""
            
            # Create a more specific prompt that asks for a single email in plain text
            prompt = f"""
Generate a single, professional email based on the following information:

Purpose: {purpose}
Tone: {tone}
Additional notes: {notes}
{ctx}

Instructions:
1. Create only ONE complete email with a clear subject line and body
2. Use the specified tone ({tone}) throughout the email
3. Make the email concise and focused on the stated purpose
4. Format your response as plain text, not JSON
5. Start with "Subject:" followed by the subject line
6. After the subject line, include a blank line and then the email body

Example format:
Subject: Meeting Request for Next Week

Hi [Name],

I hope this email finds you well. I would like to schedule a meeting...

Best regards,
[Your Name]
"""

            result = self._chat(prompt)
            
            # Parse the result to extract subject and body
            lines = result.split('\n')
            subject = ""
            body = ""
            
            # Find the subject line
            for i, line in enumerate(lines):
                if line.lower().startswith('subject:'):
                    subject = line.replace('Subject:', '').replace('subject:', '').strip()
                    # The rest of the lines after the subject line form the body
                    body = '\n'.join(lines[i+1:]).strip()
                    break
            
            # If we couldn't parse the subject, use a default
            if not subject:
                subject = f"Email regarding {purpose}"
                body = result.strip()
            
            return {"subject": subject, "body": body}

        except Exception as e:
            logger.error(f"Error generating email: {e}")
            return {"subject": "Error", "body": str(e)}

    # -----------------------------
    # Generate Follow-up Email
    # -----------------------------
    def generate_follow_up(self, original_email, days_delay: int = 3) -> Dict[str, Any]:
        """Generate a follow-up email based on an original email.
        
        Args:
            original_email: The original email object
            days_delay: Number of days to wait before sending follow-up
            
        Returns:
            Dictionary containing follow-up email subject and body
        """
        try:
            # Get the body_text attribute with backward compatibility
            body_text = getattr(original_email, 'body_text', '') or getattr(original_email, 'body', '')
            
            prompt = f"""
Create a follow-up email based on the following information:

Original Subject: {original_email.subject}
Sender: {original_email.sender}
Body Snippet: {body_text[:300]}
Follow-up after {days_delay} days.

Instructions:
1. Create only ONE complete follow-up email with a clear subject line and body
2. Format your response as plain text, not JSON
3. Start with "Subject:" followed by the subject line
4. After the subject line, include a blank line and then the email body
"""

            result = self._chat(prompt)
            
            # Parse the result to extract subject and body
            lines = result.split('\n')
            subject = ""
            body = ""
            
            # Find the subject line
            for i, line in enumerate(lines):
                if line.lower().startswith('subject:'):
                    subject = line.replace('Subject:', '').replace('subject:', '').strip()
                    # The rest of the lines after the subject line form the body
                    body = '\n'.join(lines[i+1:]).strip()
                    break
            
            # If we couldn't parse the subject, use a default
            if not subject:
                subject = f"Follow-up: {original_email.subject}"
                body = result.strip()
            
            return {"subject": subject, "body": body}

        except Exception as e:
            logger.error(f"Error generating follow-up: {e}")
            return {"subject": "Error", "body": str(e)}

    # -----------------------------
    # Generate Reply Suggestion
    # -----------------------------
    def generate_reply(self, email_text: str) -> str:
        """Generate a professional reply suggestion for an email.
        
        Args:
            email_text: The text of the email to reply to
            
        Returns:
            Suggested reply text
        """
        try:
            prompt = f"""
Write a professional reply for the following email. Provide only the reply text without any JSON formatting or additional explanations.

Original email:
{email_text}

Reply:
"""
            result = self._chat(prompt)
            return result
        except Exception as e:
            logger.error(f"Error generating reply: {e}")
            return f"Error generating reply: {str(e)}"

    # -----------------------------
    # Summarize Email
    # -----------------------------
    def summarize_text(self, email_text: str) -> str:
        """Summarize an email in 2-3 lines.
        
        Args:
            email_text: The text of the email to summarize
            
        Returns:
            Email summary
        """
        try:
            prompt = f"Summarize this email in 2-3 lines:\n\n{email_text}"
            result = self._chat(prompt)
            return result
        except Exception as e:
            logger.error(f"Error summarizing text: {e}")
            return f"Error summarizing: {str(e)}"

    # -----------------------------
    # Classify Email (Sentiment + Type + Urgency)
    # -----------------------------
    def classify_email(self, email_text: str) -> Dict[str, Any]:
        """Classify an email by sentiment, type, and urgency.
        
        Args:
            email_text: The text of the email to classify
            
        Returns:
            Dictionary containing classification results
        """
        try:
            # Use the sentiment pipeline for sentiment analysis
            sentiment_result = self.sentiment_pipeline(email_text[:512])[0]
            
            return {
                "sentiment": sentiment_result["label"].lower(),
                "sentiment_confidence": sentiment_result["score"],
                "type": self._classify_type(email_text),
                "is_urgent": self._is_urgent(email_text)
            }

        except Exception as e:
            logger.error(f"Error classifying email: {e}")
            return {"error": str(e)}

    # -----------------------------
    # Email Type Classification
    # -----------------------------
    def _classify_type(self, text: str) -> str:
        """Classify the type of email based on content.
        
        Args:
            text: The email text to classify
            
        Returns:
            Email type as a string
        """
        t = text.lower()
        
        # Define type keywords with priority
        type_keywords = [
            ("invoice", "invoice"),
            ("meeting", "meeting"),
            ("job", "job_application"),
            ("newsletter", "newsletter"),
            ("offer", "promotion"),
            ("urgent", "urgent")
        ]
        
        for keyword, email_type in type_keywords:
            if keyword in t:
                return email_type
                
        return "general"

    # -----------------------------
    # Urgency Detection
    # -----------------------------
    def _is_urgent(self, text: str) -> bool:
        """Determine if an email is urgent based on content.
        
        Args:
            text: The email text to analyze
            
        Returns:
            Boolean indicating if the email is urgent
        """
        t = text.lower()
        urgent_words = ["urgent", "asap", "immediately", "critical", "important"]
        return any(w in t for w in urgent_words)