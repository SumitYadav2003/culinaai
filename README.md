[comment]: # (You may find the following markdown cheat sheet useful: https://www.markdownguide.org/cheat-sheet/. You may also consider using an online Markdown editor such as StackEdit.) 

## Project title: *CulinaAI: An AI-Assisted Recipe Generation and Meal Personalisation System*

### Student name: *Sumit Yadav*

### Student email: *sny2@student.le.ac.uk*

### Project description: 
*CulinaAI: An AI-Assisted Recipe Generation and Meal Personalisation System is a web-based application that helps users generate personalised cooking recipes from the ingredients they already have, dietary preferences, allergies, cuisine choices, cooking time and difficulty level. The system will provide a structured user interface where users can enter recipe constraints and receive an AI-assisted recipe containing a title, ingredient list, quantities, preparation/cooking steps, estimated time, servings and dietary tags. A backend API will manage recipe generation, validation and storage, while a database will store generated recipes and user recipe history. The project will focus on building a working full-stack prototype with clear user flow, reliable input handling, and basic evaluation of whether generated recipes broadly align with selected constraints. The final deliverable will demonstrate practical AI integration within a usable recipe creation system.*

### List of requirements (objectives): 

[comment]: # (You can add as many additional bullet points as necessary by adding an additional hyphon symbol '-' at the end of each list) 

Essential:
- Develop a responsive web-based user interface that allows users to enter ingredients, dietary preferences, allergies, cuisine type, cooking time and difficulty level.
- Implement backend API endpoints to process user inputs, manage recipe generation requests and return structured recipe results.
- Integrate an AI-assisted recipe generation component that creates recipes based on user-provided constraints.
- Store generated recipes in a database, including recipe title, ingredients, instructions, cooking time, servings, dietary tags and user-selected preferences.
- Provide functionality for users to view previously generated or saved recipes through the application.
- Implement validation, error handling and testing to check that the system handles user inputs correctly and that generated recipes broadly align with selected constraints.

Desirable:
- Allow users to regenerate or modify a recipe by changing constraints such as cooking time, cuisine, spice level or dietary preference.
- Add a basic recipe rating or feedback feature so users can record whether a generated recipe was useful.
- Provide simple allergy or dietary warnings when generated recipe content may conflict with user restrictions.

Optional:
- Add a weekly meal planning feature using saved or generated recipes.
- Provide approximate nutritional information for generated recipes.
- Generate a shopping list from the ingredients required for a selected recipe.


## Information about this repository
This repository will be used individually to develop and document the CulinaAI dissertation project. The main software artefacts will be organised into separate folders, with backend API code stored in /backend, frontend user interface code stored in /frontend, database schema or migration files stored in /database, testing files stored in /tests, and supporting documentation stored in /docs. Working features will be committed regularly to GitLab with clear commit messages so that project progress can be tracked throughout development.