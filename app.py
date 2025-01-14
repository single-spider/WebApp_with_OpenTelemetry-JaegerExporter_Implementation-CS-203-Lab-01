import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.trace import SpanKind
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import ReadableSpan
import logging

# --- Flask App Initialization ---
app = Flask(__name__)
app.secret_key = 'secret'

# --- Determine app.py's directory ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Data Folder and File Paths ---
DATA_FOLDER = os.path.join(APP_DIR, 'data')
COURSE_FILE = os.path.join(DATA_FOLDER, 'course_catalog.json')
SPAN_LOG_FILE = os.path.join(DATA_FOLDER, 'spans.json')
LOG_FILE = os.path.join(DATA_FOLDER, 'app_logs.json')  # New log file path

# Create the data folder if it doesn't exist
os.makedirs(DATA_FOLDER, exist_ok=True)

# --- Logging Setup ---
# Create a logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create a console handler and set its level
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# Create a formatter for console output
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Add the console handler to the logger
logger.addHandler(console_handler)

# --- JSON Log File Handler ---
class JSONLogFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "name": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
            "filename": record.filename,
            "line_no": record.lineno,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

json_file_handler = logging.FileHandler(LOG_FILE)
json_file_handler.setLevel(logging.DEBUG)

# Create a JSON formatter and add it to the file handler
json_formatter = JSONLogFormatter()
json_file_handler.setFormatter(json_formatter)

# Add the JSON file handler to the logger
logger.addHandler(json_file_handler)

# --- Disable Flask's default request logging ---
flask_logger = logging.getLogger('werkzeug')
flask_logger.propagate = False
flask_logger.addHandler(logging.NullHandler())

# --- JSONFileSpanExporter ---
class JSONFileSpanExporter(SpanExporter):
    def __init__(self, filename=SPAN_LOG_FILE):
        self.filename = filename

    def export(self, spans):
        span_data = []
        for span in spans:
            span_dict = self._convert_span_to_dict(span)
            span_data.append(span_dict)
        ensure_directory_exists(self.filename)
        with open(self.filename, "a") as json_file:
            for span_dict in span_data:
                json.dump(span_dict, json_file, indent=4)
                json_file.write("\n")  # Add a newline for readability

    def _convert_span_to_dict(self, span):
        """Convert a span to a dictionary for JSON serialization."""
        span_dict = {
            "name": span.name,
            "context": {
                "trace_id": span.context.trace_id,
                "span_id": span.context.span_id,
                "trace_flags": span.context.trace_flags,
                "is_remote": span.context.is_remote,
            },
            "kind": str(span.kind),
            "parent_id": span.parent.span_id if span.parent else None,
            "start_time": span.start_time,
            "end_time": span.end_time,
            "status": {
                "status_code": str(span.status.status_code),
                "description": span.status.description,
            },
            "attributes": dict(span.attributes),
            "events": [
                {
                    "name": event.name,
                    "timestamp": event.timestamp,
                    "attributes": dict(event.attributes),
                }
                for event in span.events
            ],
            "links": [
                {
                    "context": {
                        "trace_id": link.context.trace_id,
                        "span_id": link.context.span_id,
                    },
                    "attributes": dict(link.attributes),
                }
                for link in span.links
            ],
            "resource": {
                "attributes": dict(span.resource.attributes),
            },
        }
        return span_dict

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        pass

# --- Utility Functions ---
def ensure_directory_exists(file_path):
    """Creates the directory for the given file path if it doesn't exist."""
    directory = os.path.dirname(file_path)
    os.makedirs(directory, exist_ok=True)

def load_courses():
    """Load courses from the JSON file."""
    with tracer.start_as_current_span("load_courses") as load_span:
        try:
            ensure_directory_exists(COURSE_FILE)  # Ensure 'data' folder exists
            if not os.path.exists(COURSE_FILE):
                load_span.set_attribute("course.file_exists", False)
                logger.warning("Course file not found.")
                return []
            with open(COURSE_FILE, 'r') as file:
                load_span.set_attribute("course.file_exists", True)
                courses = json.load(file)
                logger.info(f"Successfully loaded {len(courses)} courses from file.")
                return courses
        except Exception as e:
            load_span.record_exception(e)
            load_span.set_status(trace.Status(trace.StatusCode.ERROR))
            logger.error(f"Error loading courses: {e}")
            return []

def save_courses(data):
    """Save new course data to the JSON file."""
    with tracer.start_as_current_span("save_course") as save_span:
        try:
            ensure_directory_exists(COURSE_FILE)  # Ensure 'data' folder exists
            courses = load_courses()
            courses.append(data)
            with open(COURSE_FILE, 'w') as file:
                json.dump(courses, file, indent=4)
            save_span.set_attribute("course.saved", True)
            logger.info(f"Course '{data['name']}' saved successfully.")
        except Exception as e:
            save_span.record_exception(e)
            save_span.set_status(trace.Status(trace.StatusCode.ERROR))
            save_span.set_attribute("course.saved", False)
            logger.error(f"Error saving course: {e}")

# --- OpenTelemetry Setup ---
resource = Resource.create({"service.name": "course-catalog-service"})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

# Configure Jaeger exporter
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)

# Create JSON file exporter
json_exporter = JSONFileSpanExporter(filename=SPAN_LOG_FILE)

# Create a BatchSpanProcessor for each exporter
jaeger_span_processor = BatchSpanProcessor(jaeger_exporter)
json_span_processor = BatchSpanProcessor(json_exporter)

# Add both span processors to the tracer provider
trace.get_tracer_provider().add_span_processor(jaeger_span_processor)
trace.get_tracer_provider().add_span_processor(json_span_processor)

FlaskInstrumentor().instrument_app(app)

# --- Routes ---
@app.route('/')
def index():
    logger.info("Accessed index page.")
    return render_template('index.html')

@app.route('/catalog')
def course_catalog():
    with tracer.start_as_current_span("course_catalog", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.set_attribute("http.status_code", 200)
        span.set_attribute("user.ip", request.remote_addr)
        with tracer.start_as_current_span("load_courses") as load_span:
            courses = load_courses()
            if courses:
                span.set_attribute("course.count", len(courses))
        logger.info("Accessed course catalog page.")
        return render_template('course_catalog.html', courses=courses)

@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    if request.method == 'POST':
        with tracer.start_as_current_span("add_course", kind=SpanKind.SERVER) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", request.url)
            span.set_attribute("user.ip", request.remote_addr)

            # --- Simplified field check ---
            if not all([request.form['code'], request.form['name'], request.form['instructor']]):
                error_message = "All fields (course code, name, and instructor) are required."
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.set_attribute("http.status_code", 400)
                logger.error("User is missing a field while adding a course.")
                flash(error_message, "error")
                return render_template('add_course.html')

            # --- If all fields are present, proceed with saving ---
            course = {
                'code': request.form['code'],
                'name': request.form['name'],
                'instructor': request.form['instructor'],
                'semester': request.form['semester'],
                'schedule': request.form['schedule'],
                'classroom': request.form['classroom'],
                'prerequisites': request.form['prerequisites'],
                'grading': request.form['grading'],
                'description': request.form['description']
            }
            span.set_attribute("http.status_code", 200)
            span.set_attribute("course.code", course['code'])
            span.set_attribute("course.name", course['name'])
            save_courses(course)
            flash(f"Course '{course['name']}' added successfully!", "success")
            logger.info(f"Added course: {course['name']} ({course['code']})")
            return redirect(url_for('course_catalog'))
    logger.info("Accessed add course page.")
    return render_template('add_course.html')

@app.route('/course/<code>')
def course_details(code):
    with tracer.start_as_current_span("course_details", kind=SpanKind.SERVER) as span:
        try:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", request.url)
            span.set_attribute("user.ip", request.remote_addr)
            courses = load_courses()
            course = next((course for course in courses if course['code'] == code), None)
            if not course:
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.record_exception(Exception(f"Course not found: {code}"))
                span.set_attribute("http.status_code", 404)
                logger.warning(f"Course details not found for code: {code}")
                flash(f"No course found with code '{code}'.", "error")
                return redirect(url_for('course_catalog'))
            span.set_attribute("http.status_code", 200)
            span.set_attribute("course.code", course['code'])
            span.set_attribute("course.name", course['name'])
            logger.info(f"Accessed course details for: {course['name']} ({course['code']})")
            return render_template('course_details.html', course=course)
        except Exception as e:
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            span.record_exception(e)
            logger.error(f"Error loading course details: {e}")
            flash("An error occurred.", "error")
            return redirect(url_for('index'))

@app.route("/manual-trace")
def manual_trace():
    # Start a span manually for custom tracing
    with tracer.start_as_current_span("manual-span", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.set_attribute("http.status_code", 200)
        span.add_event("Processing request")
        logger.info("Manual trace recorded.")
        return "Manual trace recorded!", 200

@app.route("/auto-instrumented")
def auto_instrumented():
    # Automatically instrumented via FlaskInstrumentor
    logger.info("Accessed auto-instrumented page.")
    return "This route is auto-instrumented!", 200

if __name__ == '__main__':
    app.run(debug=True)
    
