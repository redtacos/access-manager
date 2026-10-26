# Access Manager Lambda Function

A Python Lambda function for managing access control, designed to run locally in a virtual environment with comprehensive test coverage.

This is far from a complete implementation, but is a good enough PoC to demonstrate the concept an feasability of the project.


## Prerequisites

- Python 3.10 or higher
- pip (Python package manager)


## Setup

Create and activate the virtual environment:

```bash
make setup
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```


## Running Tests

Run all tests with coverage reporting:

```bash
make test
```

Run tests without coverage:

```bash
. .venv/bin/activate
pytest tests/ -v
```

Run a specific test:

```bash
. .venv/bin/activate
pytest tests/test_e2e_access_flow.py::test_an_owner_approved_request_goes_from_request_to_revocation -v
```


## Development Workflow

### Activate the virtual environment:

```bash
. .venv/bin/activate   # On macOS/Linux
.venv\Scripts\activate # On Windows
```


### Run a sample Lambda invocation:

```bash
make run
```


### Deactivate the virtual environment:

```bash
deactivate
```


### Clean up (remove venv and cache files):

```bash
make clean
```


## Project Structure

```
access-manager/
├── venv/                # Virtual environment (auto-created)
├── src/                 # Source Code
├── tests/               # Tests
├── requirements.txt     # Production dependencies
├── requirements-dev.txt # Development and test dependencies
├── README.md            # This file
├── .gitignore           # Git ignore rules
└── Makefile             # Helpful make commands
```


## Available Commands

Run `make help` to see all available commands:

```
make setup       - Create virtual environment and install dependencies
make test        - Run tests with coverage
make lint        - Run code style checks
make clean       - Remove virtual environment and cache files
make run         - Run the Lambda handler locally with sample event
```
