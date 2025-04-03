##Flask Based WebAPP with Data-Logging using Open-Telemetry
Authors: Gaurav Srivastava, Divyansh Saini

## Project Overview
The **Course Information Portal** is a Flask-based web application that allows users to manage and explore a catalog of courses. It integrates OpenTelemetry for distributed tracing and telemetry data collection, providing insights into the application's performance and user interactions. The project also includes features for adding new courses, viewing course details, and exporting telemetry data to Jaeger.

---

## Features

### 1. **Add Courses to the Catalog**
- Users can add new courses to the catalog by filling out a form on the portal.
- The form requires mandatory fields such as course name, instructor, and semester.
- If any required fields are missing, the application displays an error message and logs the issue appropriately.
- Successfully submitted courses are added to the catalog, and a confirmation message is displayed to the user.

### 2. **Course Catalog and Details**
- View all courses available in the catalog on the catalog page.
- Browse detailed information about individual courses by clicking on a course from the catalog.

### 3. **OpenTelemetry Tracing**
- The application uses OpenTelemetry to trace requests across various routes:
  - Course catalog page.
  - Adding a new course.
  - Viewing course details.
- Each span includes meaningful attributes such as user IP, request methods, and course metadata.

### 4. **Exporting Telemetry Data to Jaeger**
- The portal is integrated with Jaeger for tracing and exporting telemetry data, including:
  - Total requests to each route.
  - Processing times for key operations.
  - Error counts during operations like course additions or missing fields.
- Structured logs are outputted in JSON format and categorized by levels (INFO, WARNING, ERROR).

### 5. **Code Quality**
- The code is modular, clean, and adheres to Flask development best practices.
- Comments are provided to explain key operations, including OpenTelemetry spans and attributes.

---

## Getting Started

### Prerequisites
- Python 3.8+
- Flask
- OpenTelemetry Python SDK
- Jaeger (as the tracing backend)
- pip (Python package manager)

### Installation
1. Clone this repository:
   ```bash
   gh repo clone single-spider/WebApp_with_OpenTelemetry-JaegerExporter_Implementation-CS-203-Lab-01
   ```
2. Install required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start Jaeger locally (if not already running):
   ```bash
   docker run -d --name jaeger -e COLLECTOR_ZIPKIN_HTTP_PORT=9411 -p 5775:5775/udp -p 6831:6831/udp -p 6832:6832/udp -p 5778:5778 -p 16686:16686 -p 14268:14268 -p 14250:14250 -p 9411:9411 jaegertracing/all-in-one:1.41
   ```
4. Run the application:
   ```bash
   python app.py
   ```
5. Access the application in your browser at `http://127.0.0.1:5000/`.

---

## Project Structure
```
course-information-portal/
├── app.py                  # Main Flask application file
├── data/
│   └── course_catalogue.json  # JSON file storing course data
│   └── spans.json
│   └── app_log.json
├── templates/
│   ├── index.html          # Home page template
│   ├── course_catalog.html # Course catalog page template
│   ├── course_details.html # Course details page template
│   └── add_course.html     # Add course form template
├── static/
│   └── styles.css          # CSS for styling
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation
```

---

## Usage
1. **Add a New Course**
   - Navigate to the catalog page and click on "Add a New Course."
   - Fill out the form and submit it to add the course to the catalog.

2. **View Course Catalog**
   - Browse all available courses on the catalog page.
   - Click on a course to view detailed information.

3. **Monitor Tracing Data**
   - Access Jaeger UI at `http://localhost:16686/` to view tracing data.

---

## OpenTelemetry Configuration
The application is instrumented with OpenTelemetry for tracing and telemetry data collection. Tracing spans and logs are configured with:
- FlaskInstrumentation for automatic tracing of Flask routes.
- Custom spans for operations like loading courses, handling form submissions, and rendering templates.
- Exporting telemetry data to Jaeger via the ConsoleSpanExporter and BatchSpanProcessor.

---

## Acknowledgments
- [Flask Documentation](https://flask.palletsprojects.com/)
- [OpenTelemetry Documentation](https://opentelemetry.io/)
- [Jaeger Documentation](https://www.jaegertracing.io/)

## Project Contributors
- Divyansh Saini (Lead Developer)    
- Gaurav Srivastava (Lead Developer)

