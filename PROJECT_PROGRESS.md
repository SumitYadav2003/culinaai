# CulinaAI Project Progress

## Project Title

**CulinaAI: An AI-Assisted Recipe Generation and Meal Personalisation System**

---

## Completed Core Features

* Django project setup
* PostgreSQL database connection
* Environment variable configuration using `.env`
* Secure handling of sensitive keys through `.env` and `.env.example`
* User registration
* User login
* User logout
* Protected dashboard for authenticated users
* Professional homepage
* Responsive navigation bar
* Responsive frontend layout using Django templates, Bootstrap and custom CSS
* Dynamic dashboard analytics
* Separated dashboard CSS file
* AI recipe generation using OpenAI API
* Personalised recipe generation using ingredients, cuisine, meal type, dietary preference, allergies and cooking preferences
* AI prompt construction for personalised recipe output
* Saved recipe storage in PostgreSQL
* Saved recipe detail page
* Favourite recipes
* Saved recipe search and filters
* Search and filter favourite recipes
* Recipe ratings
* Recipe feedback
* Allergy and dietary notes
* Real Gmail SMTP recipe email sharing
* Clean Django Admin recipe management
* Admin inspection for recipe data
* Admin deep inspection for AI prompt, AI response, source recipe and modification type
* Delete saved recipe with same-page confirmation modal
* Improved dashboard quick launch actions for recipe workflow
* Form validation and user-facing error handling
* Professional UI polish across homepage, dashboard, recipe generation, saved recipes and authentication pages

---

## Completed Desirable Features

* AI recipe modification
* Modified recipe preview
* Save modified recipe as a new saved recipe
* Original vs modified recipe comparison
* Recipe modification tracking in database
* Modification type tracking for healthier, cheaper, quicker, vegetarian, spicier, simpler and custom changes
* Source recipe tracking for modified recipes
* Improved saved recipe detail page with comparison and modification context
* User evaluation through ratings and feedback
* Real recipe email sharing using Gmail SMTP
* Search and filtering for saved recipes
* Search and filtering for favourite recipes
* Dashboard analytics for saved recipes, favourites and recent activity
* Improved admin management for AI-generated and modified recipes

---

## Completed Optional Enhancements

* Print/export saved recipe page
* Browser print support for saving recipes as PDF
* Saved recipe shopping list modal
* Shopping list generation from saved recipe ingredients
* Shopping list item grouping by category
* Copy shopping list to clipboard
* Print shopping list support
* Password reset by email
* Deployment-ready password reset email routing
* Real SMTP password reset email delivery
* Branded HTML password reset email template
* Plain text password reset email fallback
* Password reset request page
* Password reset confirmation page
* New password form page
* Password reset complete success page
* Login page forgot password link
* Password reset flow tested successfully with real email delivery

---

## Strong Dissertation Evidence

* AI-assisted recipe generation
* Personalisation through ingredients, cuisine, diet, allergies and user preferences
* Persistent recipe storage using PostgreSQL
* User recipe management through saved recipes and favourites
* User evaluation through ratings and feedback
* AI refinement through recipe modification
* Explainability through original vs modified recipe comparison
* Modification tracking showing how AI output changed from the original recipe
* Real email sharing through SMTP
* Real password reset email delivery through SMTP
* Admin inspection and management of recipe records
* Professional analytics dashboard
* User-centred interface design
* Responsive web design
* Clear separation of backend logic, templates, static files and database models
* Evidence of authentication, authorisation and protected user routes
* Evidence of optional feature development beyond the minimum requirements

---

## Technical and Architecture Evidence

* Django backend framework
* PostgreSQL relational database
* Django ORM models for recipe storage and user interactions
* Django authentication system
* Django built-in password reset views
* Django templates for frontend rendering
* Bootstrap and custom CSS for responsive UI
* Separated CSS files for maintainability
* Separated JavaScript file for shopping list behaviour
* OpenAI API integration for recipe generation and modification
* Gmail SMTP integration for email sharing and password reset
* Environment variable management for secret keys and credentials
* Database relationships for saved recipes, favourites, ratings, feedback and modified recipe tracking
* Admin configuration for inspecting application data
* Git version control with feature-based commits

---

## Completed Recent Commits

* Added recipe print/export view
* Added saved recipe shopping list modal
* Added password reset email flow

---

## Features Completed Against Requirement Levels

### Core Requirement Coverage

* User authentication
* Recipe generation
* Personalised recipe input
* Recipe saving
* Recipe viewing
* Recipe management
* Database persistence
* Responsive user interface
* Admin management
* Error handling
* Dashboard functionality

### Desirable Requirement Coverage

* Ratings and feedback
* Favourite recipes
* Search and filtering
* Allergy and dietary notes
* Email recipe sharing
* AI recipe modification
* Original vs modified comparison
* Dashboard analytics

### Optional Requirement Coverage

* Print/export recipe
* Shopping list generation
* Shopping list copy and print support
* Password reset by email
* Deployment-ready email templates

---

## Remaining Possible Improvements

* Edit saved recipe title or personal notes
* Weekly meal planner
* Basic nutrition estimate
* Deployment preparation for AWS
* Production email setup using AWS SES or production SMTP
* HTTPS and real domain configuration
* Test cases for views, models and forms
* Final README update
* Final dissertation screenshots and evidence collection
* Final UI polishing before submission

---

## Current Project Status

CulinaAI now has a strong completed feature set covering the core, desirable and optional project requirements. The system supports AI-assisted personalised recipe generation, persistent recipe management, user feedback, recipe refinement, real email delivery, print/export functionality, shopping list generation, password reset by email and a professional responsive interface.

The next recommended project stage is:

**Deployment preparation, testing evidence, README final update and dissertation documentation.**
