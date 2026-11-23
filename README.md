# Hospital Management System

A Streamlit chat assistant for a synthetic hospital database. Ask for a patient's lab history, find a doctor by specialty, check medicine stock, or manage an appointment. The same tools are available through a Python terminal chat.

## Try it locally

You need Python 3.14, Docker with Compose, and a Groq API key. From the repository root, run these commands in PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
cd src/hospital-mcp-assistant
python -m pip install -r requirements.txt
docker compose up -d
docker compose ps
```

Compose starts MySQL 8.4 and loads the schema and sample records when it first creates the data volume. It maps **port 3307 on your computer** to port 3306 inside the container.

Set `GROQ_API_KEY` in your environment or in a local, Git-ignored `.env` file in the application directory. Once MySQL reports healthy, launch the browser chat from that directory:

```powershell
$env:MYSQL_PORT = "3307"
python -m streamlit run streamlit_app.py
```

Open the local URL printed by Streamlit. To use the terminal chat, run `python mcp_host.py` in the same environment. Both interfaces start the MCP server automatically.

## What you can ask

| Example request | MCP tool | Behavior |
| --- | --- | --- |
| Show the details for patient 101. | `get_patient_details` | Looks up one patient by ID. |
| Show patient 101's lab history. | `get_lab_results` | Lists results, newest first. |
| Find a cardiology doctor. | `search_doctor` | Searches active doctors by full or partial specialty. |
| How much Paracetamol is in stock? | `check_medicine_stock` | Looks up the quantity by exact medicine name. |
| Book patient 102 with doctor 4 on 2030-02-20 at 10:30. | `schedule_appointment` | Requests approval and checks the doctor's time slot before booking. |
| Cancel appointment 1. | `cancel_appointment` | Requests approval and cancels by appointment ID. |

## How a request works

For a question like “Show patient 101's lab history,” the host discovers the MCP server's tools and passes their input schemas to Groq. Groq selects `get_lab_results` and supplies the patient ID. The Python client sends that call to the server over standard input and output. The server validates the input, runs a parameterized MySQL query, and returns the result. The host sends the result back to Groq to compose the reply.

Appointment changes add a review step. The user sees the proposed arguments and can approve or decline them. The repository records successful changes in `appointment_audit` within the same transaction as the appointment update.

## Project structure

```text
.
├── .python-version                 # Python version for the workspace
├── pyproject.toml                  # Root Python project metadata
└── src/hospital-mcp-assistant/
    ├── streamlit_app.py            # Browser chat, model picker and approval controls
    ├── mcp_host.py                 # Terminal chat entry point
    ├── mcp_server.py               # Standalone MCP server entry point
    ├── hospital_mcp/
    │   ├── host.py                 # Groq tool selection and execution loop
    │   ├── client.py               # MCP subprocess and session management
    │   ├── server.py               # FastMCP server setup
    │   ├── tools.py                # Six hospital tool definitions
    │   ├── repository.py           # SQL queries and appointment transactions
    │   ├── db.py                   # MySQL connection pool
    │   ├── config.py               # Groq and MySQL environment settings
    │   ├── validators.py           # Input and appointment-time validation
    │   └── errors.py               # Application exceptions
    ├── database/
    │   ├── schema.sql              # Tables, foreign keys and indexes
    │   └── seed.sql                # Fictional hospital records
    ├── tests/                      # Validator and repository unit tests
    ├── docker-compose.yml          # Local MySQL service and persistent volume
    └── requirements.txt            # Application dependencies
```

## Running the tests

From `src/hospital-mcp-assistant`, run:

```powershell
python -m unittest discover -s tests -v
```

The unit tests exercise validation and repository behavior using test doubles. They run independently of Docker and Groq.
