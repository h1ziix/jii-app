# Student Task Manager

Student Task Manager is a polished university-level web application built with Flask, SQLite, HTML, CSS, and Jinja2. It helps students organize academic work by subject, monitor deadlines, set priorities, track progress, and quickly identify overdue tasks.

## Features

- User registration, login, and logout
- Session-based authentication with protected routes
- Secure password hashing with Werkzeug
- Create, edit, and delete personal tasks
- Subject categorization for academic organization
- Deadline management with overdue highlighting
- Priority and status tracking
- Dashboard with summary statistics
- Filtering, searching, and sorting
- Owner-only task editing and deletion
- Responsive modern interface
- Automatic SQLite database creation on first run
- Flash messages for user feedback
- Bilingual interface with Russian and Kazakh support
- Session-based language switching that stays active while browsing
- QR-based test creation for teachers
- Public student test access by secure token and QR code
- Automatic scoring, result saving, and teacher result analytics

## Tech Stack

- Backend: Python Flask
- Database: SQLite
- Frontend: HTML, CSS, Jinja2
- Authentication: Flask session-based authentication
- Password Security: `werkzeug.security`
- Localization: custom lightweight translation dictionary in Python
- QR Generation: `qrcode` with Pillow backend

## Project Structure

```text
student-task-manager/
|-- app.py
|-- requirements.txt
|-- README.md
|-- student_task_manager.db   # auto-created after first run
|-- static/
|   `-- css/
|       `-- style.css
`-- templates/
    |-- base.html
    |-- home.html
    |-- register.html
    |-- login.html
    |-- dashboard.html
    |-- task_form.html
    |-- statistics.html
    `-- tests/
        |-- manage_tests.html
        |-- test_form.html
        |-- test_detail.html
        |-- question_form.html
        |-- student_start.html
        |-- student_take.html
        |-- student_result.html
        `-- results_dashboard.html
```

## Installation

1. Open a terminal in the project folder.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the application:

```bash
python app.py
```

4. Open the local URL shown in the terminal, usually:

```text
http://127.0.0.1:5000
```

## Multilingual Support

- Default language: `ru` (Russian)
- Supported languages:
  - `ru` = Russian
  - `kk` = Kazakh
- Use the language switcher in the navigation bar to change the interface language.
- The selected language is stored in the Flask session, so it stays active while the user continues browsing.
- If an invalid language code is requested, the app automatically falls back to Russian.

## Notes

- The SQLite database file is created automatically the first time the app runs.
- A development secret key is included so the app works immediately for project demonstration.
- For real deployment, set a strong `SECRET_KEY` environment variable.
- Existing database logic, routes, authentication flow, and task CRUD behavior remain unchanged.
- The testing module adds normalized SQLite tables for tests, questions, options, attempts, and attempt answers.
- QR code images are generated automatically inside `static/qr/`.

## QR Testing Module

- Logged-in users can open the `Tests` section in the navbar to create and manage QR-based tests.
- Each test can include multiple questions, four answer options per question, one correct answer, and custom points.
- Students can open the public test page by token or QR code, enter their details, complete the test, and receive an automatic result page.
- Every submission is saved immediately to SQLite with score, percentage, correct answers, wrong answers, and per-question selections.
- Teachers can review all attempts in the results dashboard with filters, average score, highest score, and lowest score.

## Demonstration Flow

1. Create a new student account.
2. Add tasks for different subjects.
3. Set deadlines, priorities, and statuses.
4. Use the dashboard filters and sorting controls.
5. Switch between Russian and Kazakh using the navbar.
6. Create a QR-based test in the `Tests` section and add questions.
7. Open the student test page or scan the generated QR code.
8. Submit a student attempt and review the saved result in the teacher results dashboard.
9. Review task analytics on the statistics page.

This project is ready to present as a full student coursework submission or university defense demo.
