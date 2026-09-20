# CulinaAI — AI-Assisted Recipe Generation and Meal Personalisation System

![Django CI](https://github.com/SumitYadav2003/culinaai/actions/workflows/django-ci.yml/badge.svg)

**[Live Demo → culinaai.onrender.com](https://culinaai.onrender.com)**
*(hosted on a free tier — the first load may take 30-60 seconds if the app has been idle)*

CulinaAI is a full-stack web application that generates personalised cooking recipes from a user's available ingredients, dietary needs, allergies, cuisine preference, cooking time and servings. It integrates the OpenAI API for recipe generation and validates every generated recipe against safety and quality checks before it ever reaches a user.

Built as an MSc Individual Dissertation project at the University of Leicester (Jun 2026 – Sep 2026).

## Key Features

- **AI-powered recipe generation** across seven personalisation parameters: ingredients, cuisine, diet, allergies, cooking time, servings and equipment.
- **8-point automated validation engine** that screens every AI-generated recipe for allergy safety, dietary compliance, structural correctness, ingredient matching and equipment constraints before it's stored or shown to the user.
- **Smart Pantry** with expiry tracking, matching what's on hand against recipe requirements.
- **Refrigerator-scan ingredient detection** to populate the pantry automatically.
- **Recipe modification with side-by-side revalidation** — change a constraint and see the updated recipe re-checked against the same safety rules.
- **Real-time interactive cooking assistant** that walks users through a recipe step by step.
- User accounts with saved recipes, favourites, and recipe history.

## Tech Stack

**Backend:** Django, PostgreSQL
**Frontend:** JavaScript, Bootstrap, Django templates
**AI Integration:** OpenAI API (REST)
**Version Control:** Git

## Requirements Delivered

All **29 functional requirements** and **10 non-functional requirements** defined for the project were met and verified — see the full dissertation report for the complete requirements traceability matrix.

## Testing & Quality

The system was verified through **64 structured test scenarios across 6 categories**, with a **100% pass rate**:

| Category | Scenarios |
|---|---|
| Functional | 21 |
| Interface / Usability | 10 |
| AI-Validation | 10 |
| Pantry / Shopping | 9 |
| Integration | 7 |
| Recipe Modification | 7 |

Automated unit tests (Django `TestCase`) cover core authentication flows; the remaining scenarios above were executed as structured manual/functional testing, documented in full in the dissertation report.

## Getting Started

```bash
# Clone the repository
git clone https://github.com/SumitYadav2003/culinaai.git
cd culinaai

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables (see .env.example)
# - DATABASE credentials (PostgreSQL)
# - SECRET_KEY
# - OPENAI_API_KEY

# Run migrations
python manage.py migrate

# Run the test suite
python manage.py test

# Start the development server
python manage.py runserver
```

## Author

**Sumit Yadav**
MSc Advanced Computer Science, University of Leicester
[LinkedIn](https://linkedin.com/in/yadavsumit2003) · [GitHub](https://github.com/SumitYadav2003)
