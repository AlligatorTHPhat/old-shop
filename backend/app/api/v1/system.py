import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, get_db
from app.crud.admin import crud_admin
from app.models import User
from app.schemas import ContactMessageCreate, SystemFeedbackCreate, SystemFeedbackResponse
from app.services.contact_relay import forward_contact_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["system"])


@router.post("/feedback", response_model=SystemFeedbackResponse, status_code=status.HTTP_201_CREATED)
def post_feedback(
    feedback_in: SystemFeedbackCreate,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Feedback from a logged-in user, or from a guest who leaves an email."""
    if not current_user and not feedback_in.guest_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Guest email required for non-authenticated users"
        )
    return crud_admin.create_feedback(db, feedback_in, user_id=current_user.user_id if current_user else None)


@router.post("/contact", response_model=SystemFeedbackResponse, status_code=status.HTTP_201_CREATED)
def post_contact_message(
    message_in: ContactMessageCreate,
    background_tasks: BackgroundTasks,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Contact form: stored as feedback, then relayed to the Apps Script helpdesk sheet."""
    subject = message_in.subject or "Liên hệ từ website"
    content = f"{message_in.message}\n\n— {message_in.full_name} | {message_in.phone or 'N/A'}"
    feedback = crud_admin.create_feedback(
        db,
        SystemFeedbackCreate(guest_email=message_in.email, subject=subject, content=content),
        user_id=current_user.user_id if current_user else None,
    )

    background_tasks.add_task(
        forward_contact_message,
        {
            "feedbackId": feedback.feedback_id,
            "fullName": message_in.full_name,
            "email": message_in.email,
            "phone": message_in.phone or "",
            "subject": subject,
            "message": message_in.message,
            "source": "web",
        },
    )
    logger.info("Contact message received", extra={"feedback_id": feedback.feedback_id})
    return feedback
