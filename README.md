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
checkout and payment modify.
track his order
All business logic and data persistence are handled by Django.







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

## telegram bot view
![WhatsApp Image 2026-01-11 at 9 17 02 PM](https://github.com/user-attachments/assets/ff668087-8f7e-4867-b2a7-fa0e3a0bb0c3)

![WhatsApp Image 2026-01-11 at 9 17 30 PM](https://github.com/user-attachments/assets/8c8bed94-5bd1-4846-a10c-65a45e63dfc5)



![WhatsApp Image 2026-01-11 at 9 17 31 PM](https://github.com/user-attachments/assets/077eb09c-5548-418c-a718-0ffa6e6d3784)


![WhatsApp Image 2026-01-11 at 9 17 32 PM](https://github.com/user-attachments/assets/6580ccc2-7ca2-49c8-950f-48c57a2fc491)

![WhatsApp Image 2026-01-11 at 9 17 33 PM](https://github.com/user-attachments/assets/7e15f8c1-cf52-4247-8250-12389a99f6bd)


![WhatsApp Image 2026-01-11 at 9 17 34 PM](https://github.com/user-attachments/assets/a02d0336-600b-4e4c-818b-dc40e84f93a4)


![WhatsApp Image 2026-01-11 at 9 17 35 PM](https://github.com/user-attachments/assets/8e1d3f23-2aaa-4bd8-bdb6-8ccd966de2c8)

![WhatsApp Image 2026-01-11 at 9 17 36 PM](https://github.com/user-attachments/assets/65aacf8c-1292-4433-85b0-3103bd10ac36)

![WhatsApp Image 2026-01-11 at 9 17 37 PM](https://github.com/user-attachments/assets/9bf50483-aa68-4e7a-a613-22097e1ab0df)

