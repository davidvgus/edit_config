# Basic Web Application

A simple web application built with Flask, featuring a clean and responsive design using Bootstrap.

## Features

- Modern responsive design with Bootstrap 5
- Clean project structure
- Template inheritance with Jinja2
- Environment variable support
- Ready-to-use navigation and layout

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

## Installation

1. Clone the repository:
```bash
git clone <your-repository-url>
cd <repository-name>
```

2. Create a virtual environment:
```bash
python -m venv venv
```

3. Activate the virtual environment:
- On Windows:
```bash
venv\Scripts\activate
```
- On macOS/Linux:
```bash
source venv/bin/activate
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Create a `.env` file in the root directory and add your configuration:
```
SECRET_KEY=your-secret-key-here
```

## Running the Application

1. Make sure your virtual environment is activated
2. Run the Flask application:
```bash
python app.py
```
3. Open your browser and navigate to `http://localhost:5000`

## Project Structure

```
.
├── app.py              # Main application file
├── requirements.txt    # Python dependencies
├── .env               # Environment variables (create this)
├── .gitignore         # Git ignore file
└── templates/         # HTML templates
    ├── base.html      # Base template with common layout
    ├── index.html     # Home page template
    └── about.html     # About page template
```

## Development

To run the application in development mode with debug features:

```bash
flask run --debug
```

## Contributing

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 