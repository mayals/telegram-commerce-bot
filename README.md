🛒 Telegram Commerce Bot (Django + Telegram)

A Telegram-based e-commerce bot built with Django and python-telegram-bot, allowing users to browse products, manage a cart, and place orders directly inside Telegram.
The bot is fully integrated with Django models and services, following clean architecture and separation of concerns.


📌 Project Overview
This project demonstrates how to build a real-world Telegram commerce system using Django as the backend and Telegram as the user interface.

Users can:
Browse product categories
View products
Add products to a cart
Update cart quantities
Place orders via Telegram
All business logic and data persistence are handled by Django.


🧠 Architecture
telegram-commerce-bot/

│
├── core/                   # Django project settings
├── shop/                   # Main app (products, cart, orders)
│   ├── models.py
│   ├── services/
│   │   ├── cart_service.py
│   │   ├── order_service.py
│   ├── admin.py
│   ├── migrations/
│
├── bot.py                  # Telegram bot entry point
├── manage.py
├── requirements.txt
└── README.md




Key Design Principles
Service Layer Pattern (business logic outside views)
Django ORM for database access
Telegram bot as a standalone interface
Clean separation between bot logic and backend logic


⚙️ Technologies Used
Backend
Python 3
Django
Django ORM
SQLite (default, easily replaceable)
Telegram
python-telegram-bot
Inline keyboards
Callback queries
Stateful user interactions


Architecture & Patterns

Service-based architecture

Reusable business logic

Standalone bot integration with Django



📦 Main Python Packages
Django
python-telegram-bot
asgiref
python-dotenv (optional)
(See requirements.txt for full list)


🚀 How to Run the Project Locally
1️⃣ Clone the repository
git clone https://github.com/mayals/telegram-commerce-bot.git
cd telegram-commerce-bot

2️⃣ Create and activate virtual environment
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux / Mac

3️⃣ Install dependencies
pip install -r requirements.txt

4️⃣ Configure Django
Run migrations:
python manage.py migrate

Create admin user:
python manage.py createsuperuser

(Optional) Run Django admin:
python manage.py runserver

5️⃣ Create Telegram Bot
Open Telegram
Search for @BotFather
Create a new bot
Copy the Bot Token

6️⃣ Set Environment Variables
Create .env file or set environment variable:
TELEGRAM_BOT_TOKEN=your_bot_token_here
DJANGO_SETTINGS_MODULE=core.settings

7️⃣ Run the Telegram Bot
python bot.py

✅ Your bot is now live on Telegram.

🧪 Features Implemented
Category listing
Product listing
Add to cart
View cart
Update quantity
Order creation
Database-backed cart system
Django admin panel for managing products

🧑‍💻 Admin Panel
Access Django admin to manage:
Categories
Products
Orders
Cart items

http://127.0.0.1:8000/admin/








