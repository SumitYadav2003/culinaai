[comment]: # (You may find the following markdown cheat sheet useful: https://www.markdownguide.org/cheat-sheet/. You may also consider using an online Markdown editor such as StackEdit.) 

## Project title: *CulinaAI: An AI-Assisted Recipe Generation and Meal Personalisation System*

### Student name: *Sumit Yadav*

### Student email: *sny2@student.le.ac.uk*

### Project description: 
*CulinaAI: An AI-Assisted Recipe Generation and Meal Personalisation System is a web-based application that helps users generate personalised cooking recipes from the ingredients they already have, dietary preferences, allergies, cuisine choices, meal type, cooking time and difficulty level. The system will provide a structured user interface where users can register, log in, enter recipe constraints and receive an AI-assisted recipe containing a title, ingredient list, quantities, preparation/cooking steps, estimated time, servings and dietary tags. A backend will manage authentication, recipe generation, validation and storage, while a database will store users, generated recipes, favourite recipes, ratings and feedback. The project will focus on building a working full-stack prototype with clear user flow, reliable input handling and basic evaluation of whether generated recipes broadly align with selected constraints.*

### List of requirements (objectives): 

[comment]: # (You can add as many additional bullet points as necessary by adding an additional hyphon symbol '-' at the end of each list) 

Essential:
- Develop a responsive web-based user interface that allows users to register, log in, log out, and enter ingredients, dietary preferences, allergies, cuisine type, meal type, cooking time and difficulty level.
- Implement basic user authentication so users can securely manage their own saved recipe history.
- Implement backend functionality to process user inputs, manage recipe generation requests and return structured recipe results.
- Integrate an AI-assisted recipe generation component that creates recipes based on user-provided constraints.
- Store user accounts and generated recipes in a database, including recipe title, ingredients, instructions, cooking time, servings, dietary tags and user-selected preferences.
- Provide functionality for authenticated users to save, view and manage their generated recipes, including marking recipes as favourites.
- Configure an admin management interface to manage core records such as users, recipes, cuisines, diet preferences, meal types, ingredients, ratings, feedback and favourite recipes
- Implement validation, error handling and testing to check that authentication, user inputs, database operations and generated recipes work correctly and broadly align with selected constraints.

Desirable:
- Allow users to regenerate or modify a recipe by changing constraints such as cooking time, cuisine type, spice level, dietary preference or available ingredients..
- Add a basic recipe rating and feedback feature so users can record whether a generated recipe was useful, suitable and easy to follow..
- Provide simple allergy or dietary warnings when generated recipe content may conflict with the user’s selected restrictions.
- Allow users to send generated or saved recipes to an email address provided by the user.
- Allow authenticated users to search and filter saved recipes by cuisine, meal type, dietary preference or favourite status.
- Provide a simple user dashboard showing recent recipes, saved recipes and favourite recipes.

Optional:
- Add a weekly meal planning feature using saved or generated recipes.
- Provide approximate nutritional information for generated recipes.
- Generate a shopping list from the ingredients required for a selected recipe.
- Add email verification or password reset functionality for improved account management.

## Information about this repository
This repository will be used individually to develop and document the CulinaAI dissertation project. The main software artefacts will be organised into separate folders, with backend application code stored in /backend, frontend user interface files stored in /frontend, database-related files stored in /database, testing files stored in /tests, and supporting documentation stored in /docs. Working features will be committed regularly to GitLab with clear commit messages so that project progress can be tracked throughout development.