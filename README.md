# 📧 AI-Powered Email Generation & Automation Dashboard

A Flask-based dashboard for Gmail-connected email workflows: inbox management, AI-assisted drafting, classification, auto-replies, and follow-up automation.

---

## ✨ Features

- **Gmail OAuth Integration**
  - Connect/disconnect flow per user
  - Secure OAuth2 authentication
  
- **Inbox Management**
  - Inbox view with pagination, refresh, and search
  - Compose and send emails (CC/BCC + attachments)
  
- **Email Management**
  - Save and manage drafts and sent emails
  - Email threading and conversation view
  
- **AI-Powered Capabilities**
  - AI-powered email generation
  - Summarization and reply suggestions
  - Intelligent email classification workflows
  
- **Automation Features**
  - Rule-based auto-reply templates and logs
  - Follow-up scheduling and execution
  - Background scheduler for automation tasks

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend Framework** | Flask, Flask-Login, Flask-SQLAlchemy, Flask-Migrate |
| **Database** | SQLite (development), PostgreSQL-ready configuration |
| **Email API** | Gmail API (OAuth2) |
| **Task Scheduler** | APScheduler |
| **AI Models** | Groq + Transformers |
| **Frontend** | Jinja templates + static JS/CSS |

---

## 📁 Project Structure

```
.
├── app/
│   ├── models/                 # Database models
│   ├── routes/                 # Flask routes & endpoints
│   ├── services/               # Business logic services
│   ├── templates/              # Jinja HTML templates
│   ├── utils/                  # Utility functions
│   ├── __init__.py            # App initialization
│   ├── cli.py                 # CLI commands
│   └── tasks.py               # Background tasks
├── migrations/                 # Database migrations
├── config.py                   # Configuration settings
├── run.py                      # Entry point
├── requirements.txt            # Dependencies
└── .env                        # Environment variables (not committed)
```

---

## 📋 Prerequisites

- **Python 3.10+**
- **Google Cloud project** with Gmail API enabled
- **OAuth client credentials** JSON file
- **AI provider API key** (for AI features)

---

## 🚀 Setup Instructions

### 1. Create and Activate Virtual Environment

**Windows:**
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
# Flask Configuration
FLASK_ENV=development
SECRET_KEY=your_secret_key_here
SECURITY_PASSWORD_SALT=your_password_salt_here

# Database Configuration
DATABASE_URL=sqlite:///dev.db

# AI Provider Configuration
GROQ_API_KEY=your_groq_api_key_here

# Scheduler Configuration
SCHEDULER_TIMEZONE=Asia/Kolkata

# Email Check Intervals (in minutes)
EMAIL_CHECK_INTERVAL_MINUTES=10
FOLLOW_UP_CHECK_INTERVAL_MINUTES=1
AUTO_REPLY_CHECK_INTERVAL_MINUTES=5

# Gmail OAuth Configuration
GMAIL_CLIENT_SECRETS_FILE=/absolute/path/to/client_secrets.json
```

### 4. Run Database Migrations

```bash
flask --app run.py db upgrade
```

### 5. Start the Application

```bash
python run.py
```

**Access the dashboard:** `http://127.0.0.1:5000`

---

## 🔐 Gmail OAuth Setup

### Step-by-Step Instructions:

1. **Enable Gmail API**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Search for "Gmail API" and enable it

2. **Create OAuth Client ID**
   - Navigate to "Credentials" in Google Cloud Console
   - Click "Create Credentials" → "OAuth Client ID"
   - Choose "Web application"
   - Add the following redirect URI:
     ```
     http://127.0.0.1:5000/auth/gmail/callback
     ```

3. **Download OAuth Credentials**
   - Download the credentials JSON file
   - Save it locally (do not commit to version control)
   - Reference the file path in your `.env`:
     ```env
     GMAIL_CLIENT_SECRETS_FILE=/path/to/client_secrets.json
     ```

4. **Security Note**
   - Keep your credentials file private
   - Never commit credentials to your repository
   - Use environment variables to reference file paths

---

## 🎯 Useful CLI Commands

Manage your application with these Flask CLI commands:

```bash
# Database Management
flask --app run.py init-db              # Initialize database
flask --app run.py reset-db             # Reset database

# Email Processing
flask --app run.py sync-emails          # Sync emails from Gmail
flask --app run.py process-classifications  # Process email classifications

# Automation Tasks
flask --app run.py process-auto-replies      # Process auto-reply rules
flask --app run.py process-follow-ups        # Execute follow-up tasks
flask --app run.py check-scheduled-auto-replies  # Check scheduled replies

# Scheduler Management
flask --app run.py test-scheduler       # Test scheduler functionality
flask --app run.py start-scheduler      # Start background scheduler
flask --app run.py stop-scheduler       # Stop background scheduler
```

---

## 📚 Usage

1. **Login/Register** - Create your account
2. **Connect Gmail** - Authorize with your Gmail account
3. **View Inbox** - Browse your Gmail inbox with search and pagination
4. **Compose Emails** - Draft and send emails with attachments
5. **Use AI Features** - Generate, summarize, or get reply suggestions
6. **Set Up Automation** - Create auto-reply templates and follow-up schedules
7. **Monitor Dashboard** - Track automated tasks and email metrics

---

## 🔄 How It Works

### Email Workflow
- **Sync**: Background scheduler periodically syncs emails from Gmail
- **Process**: Emails are classified, summarized, and stored
- **Automate**: Auto-replies and follow-ups execute based on rules
- **Display**: Dashboard shows real-time inbox status and automation logs

### AI Integration
- Uses **Groq API** for fast email generation
- **Transformers** for text classification and summarization
- Intelligent suggestions for email replies

---

## 🚢 Deployment

The application is ready for deployment on platforms like:

- **Render** - Recommended for quick deployment
- **Heroku**
- **AWS (EC2, Elastic Beanstalk)**
- **DigitalOcean App Platform**

### Deployment Checklist
- [ ] Set `FLASK_ENV=production`
- [ ] Use strong `SECRET_KEY` and `SECURITY_PASSWORD_SALT`
- [ ] Configure PostgreSQL database
- [ ] Set up environment variables in hosting platform
- [ ] Enable HTTPS/SSL
- [ ] Configure Gmail OAuth redirect URIs for production domain
- [ ] Set up email notifications for scheduled tasks

---

## 🔮 Future Improvements

- [ ] Multi-language email generation
- [ ] Advanced email analytics and reporting
- [ ] Integration with other email providers (Outlook, Yahoo)
- [ ] Machine learning model for spam detection
- [ ] Custom AI model fine-tuning
- [ ] Real-time WebSocket notifications
- [ ] Team collaboration features
- [ ] Mobile app support
- [ ] Email template builder
- [ ] Advanced filtering and tagging system

---

## 📝 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## 👤 Author

**Saxon Sibi**  
- GitHub: [@saxonsibi](https://github.com/saxonsibi)
- Project: [AI-Powered Email Generation & Automation Dashboard](https://github.com/saxonsibi/AI-Powered-Email-Generation-Automation-Dashboard)

---

## 📞 Support & Contributions

For issues, feature requests, or contributions:
1. Open an issue on GitHub
2. Submit a pull request
3. Contact the author

---

**Made with ❤️ for email automation**
