import json
import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.trace import SpanKind
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import ReadableSpan

# --- Flask App Initialization ---
app = Flask(__name__)
app.secret_key = 'secret'

# --- Determine app.py's directory ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Data Folder and File Paths ---
DATA_FOLDER = os.path.join(APP_DIR, 'data')
COURSE_FILE = os.path.join(DATA_FOLDER, 'course_catalog.json')
SPAN_LOG_FILE = os.path.join(DATA_FOLDER, 'spans.json')
APP_LOG_FILE = os.path.join(DATA_FOLDER, 'app_log.json')  # File to store application logs

# Create the data folder if it doesn't exist
os.makedirs(DATA_FOLDER, exist_ok=True)

# --- Logging Setup ---
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

formatter = logging.Formatter(
    '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
)

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
log.addHandler(console_handler)

# File Handler
file_handler = logging.FileHandler(APP_LOG_FILE)
file_handler.setFormatter(formatter)
log.addHandler(file_handler)

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
                json_file.write("\n")

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
            ensure_directory_exists(COURSE_FILE)
            if not os.path.exists(COURSE_FILE):
                load_span.set_attribute("course.file_exists", False)
                log.info("Course catalog file does not exist.")
                return []
            with open(COURSE_FILE, 'r') as file:
                load_span.set_attribute("course.file_exists", True)
                courses = json.load(file)
                log.info("Courses loaded successfully.")
                return courses

        except Exception as e:
            load_span.record_exception(e)
            load_span.set_status(trace.Status(trace.StatusCode.ERROR))
            log.error(f"Error loading courses: {e}")
            return []

def save_courses(data):
    """Save new course data to the JSON file."""
    with tracer.start_as_current_span("save_course") as save_span:
        try:
            ensure_directory_exists(COURSE_FILE)
            courses = load_courses()
            courses.append(data)
            with open(COURSE_FILE, 'w') as file:
                json.dump(courses, file, indent=4)
            save_span.set_attribute("course.saved", True)
            log.info(f"Course '{data['name']}' saved successfully.")
        except Exception as e:
            save_span.record_exception(e)
            save_span.set_status(trace.Status(trace.StatusCode.ERROR))
            save_span.set_attribute("course.saved", False)
            log.error(f"Error saving course: {e}")

# --- OpenTelemetry Setup ---
resource = Resource.create({"service.name": "course-catalog-service"})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

# --- Configure Jaeger Exporter ---
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",  # Replace with your Jaeger agent host
    agent_port=6831,             # Replace with your Jaeger agent port
)

# --- Create JSON File Exporter ---
json_exporter = JSONFileSpanExporter(filename=SPAN_LOG_FILE)

# --- Create BatchSpanProcessors ---
jaeger_span_processor = BatchSpanProcessor(jaeger_exporter)
json_span_processor = BatchSpanProcessor(json_exporter)

# --- Add Span Processors to Tracer Provider ---
trace.get_tracer_provider().add_span_processor(jaeger_span_processor)
trace.get_tracer_provider().add_span_processor(json_span_processor)

FlaskInstrumentor().instrument_app(app)

# --- Routes ---
@app.route('/')
def index():
    log.info("Rendering index page.")
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
            log.info("Rendering course catalog page.")
        return render_template('course_catalog.html', courses=courses)

@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    if request.method == 'POST':
        with tracer.start_as_current_span("add_course", kind=SpanKind.SERVER) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", request.url)
            span.set_attribute("user.ip", request.remote_addr)

            # Check if any required field is empty
            if any(not request.form.get(field) for field in ['code', 'name', 'instructor', 'semester', 'schedule', 'classroom', 'prerequisites', 'grading', 'description']):
                error_message = "Missing required field(s) in the form."
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                span.set_attribute("http.status_code", 400)
                span.record_exception(Exception(error_message))
                log.error(error_message)
                flash(error_message, "error")
                return render_template('add_course.html')

            course = {
                'code': request.form['code'],
                'name': request.form['name'],
                'instructor': request.form['instructor'],
                'semester': request.form['semester'],
                'schedule': request.form['schedule'],
                'classroom': request.form.get('classroom', ''),
                'prerequisites': request.form.get('prerequisites', ''),
                'grading': request.form.get('grading', ''),
                'description': request.form.get('description', '')
            }
            span.set_attribute("http.status_code", 200)
            span.set_attribute("course.code", course['code'])
            span.set_attribute("course.name", course['name'])
            save_courses(course)
            flash(f"Course '{course['name']}' added successfully!", "success")
            log.info(f"Course '{course['name']}' added successfully by user {request.remote_addr}.")
            return redirect(url_for('course_catalog'))
    log.info("Rendering add course page.")
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
                log.warning(f"Course not found: {code}")
                flash(f"No course found with code '{code}'.", "error")
                return redirect(url_for('course_catalog'))

            span.set_attribute("http.status_code", 200)
            span.set_attribute("course.code", course['code'])
            span.set_attribute("course.name", course['name'])
            log.info(f"Rendering details page for course: {course['name']}.")
            return render_template('course_details.html', course=course)
        except Exception as e:
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            span.record_exception(e)
            span.set_attribute("http.status_code", 500)
            log.error(f"An error occurred while accessing course details: {e}")
            flash("An error occurred.", "error")
            return redirect(url_for('index'))

@app.route("/manual-trace")
def manual_trace():
    with tracer.start_as_current_span("manual-span", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.set_attribute("http.status_code", 200)
        span.add_event("Processing request")
        log.info("Manual trace recorded.")
        return "Manual trace recorded!", 200

@app.route("/auto-instrumented")
def auto_instrumented():
    log.info("Auto-instrumented route accessed.")
    return "This route is auto-instrumented!", 200

@app.route('/contacts')
def contacts():
    log.info("Rendering contacts page.")
    return render_template('contact.html')

if __name__ == '__main__':
    app.run(debug=True)
