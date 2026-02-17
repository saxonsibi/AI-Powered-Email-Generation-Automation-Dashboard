from app import db
from datetime import datetime

class AutomationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rule_id = db.Column(db.Integer, db.ForeignKey('automation_rules.id'))  # Fix: Use 'automation_rules' (plural) instead of 'automation_rule'
    email_id = db.Column(db.Integer, db.ForeignKey('emails.id'))
    action_type = db.Column(db.String(50))  # 'auto_reply', 'follow_up'
    status = db.Column(db.String(50))  # 'success', 'failed'
    message = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<AutomationLog {self.id}: {self.action_type} - {self.status}>'