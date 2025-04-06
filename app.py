import json
import os
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Dict, List

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

# Load environment variables
load_dotenv()

# Configuration for file uploads
UPLOAD_FOLDER = "uploads"
ARCHIVE_FOLDER = "archives"
NEW_CONFIGS_FOLDER = "new_configs"
ARCHIVE_METADATA = "archive_metadata.json"
NEW_CONFIGS_METADATA = "new_configs_metadata.json"
REQUIRED_FILES = {"file1": "group_config.xml", "file2": "thumbnail_settings.xml"}

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-please-change")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Create upload, archive, and new configs directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
os.makedirs(NEW_CONFIGS_FOLDER, exist_ok=True)


def validate_file(file, expected_name):
    if file.filename == "":
        return False
    return file.filename.lower() == expected_name.lower()


def parse_group_config() -> Dict[str, List[dict]]:
    """Parse group_config.xml and return dict of access_codes and their systems with full details"""
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], REQUIRED_FILES["file1"])
    if not os.path.exists(filepath):
        return {}

    # Use a list of tuples to maintain order
    student_systems_list = []
    tree = ET.parse(filepath)
    root = tree.getroot()

    # Find all students across all groups
    for group in root.findall("group"):
        students = group.find("students")
        if students is not None:
            for student in students.findall("student"):
                access_code = (
                    student.find("access_code").text
                    if student.find("access_code") is not None
                    else None
                )
                if access_code:
                    systems = []
                    systems_elem = student.find("systems")
                    if systems_elem is not None:
                        for system in systems_elem.findall("system"):
                            system_info = {
                                "name": (
                                    system.find("name").text
                                    if system.find("name") is not None
                                    else ""
                                ),
                                "ip": (
                                    system.find("ip").text
                                    if system.find("ip") is not None
                                    else ""
                                ),
                                "os_type": (
                                    system.find("os_type").text
                                    if system.find("os_type") is not None
                                    else ""
                                ),
                                "image_name": (
                                    system.find("image_name").text
                                    if system.find("image_name") is not None
                                    else ""
                                ),
                                "group_id": (
                                    group.find("group_id").text
                                    if group.find("group_id") is not None
                                    else ""
                                ),
                                "group_name": (
                                    group.find("group_name").text
                                    if group.find("group_name") is not None
                                    else ""
                                ),
                            }
                            systems.append(system_info)
                    student_systems_list.append((access_code, systems))

    # Sort by the last two characters of the access code
    student_systems_list.sort(key=lambda x: x[0][-2:] if x[0] else "")

    # Convert back to dictionary while maintaining order
    return dict(student_systems_list)


def parse_thumbnail_settings() -> Dict[str, List[dict]]:
    """Parse thumbnail_settings.xml and return dict of access_codes and their systems"""
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], REQUIRED_FILES["file2"])
    if not os.path.exists(filepath):
        return {}

    thumbnail_systems = {}
    tree = ET.parse(filepath)
    root = tree.getroot()

    for item in root.findall(".//thumbnail_item"):
        access_code = (
            item.find("access_code").text
            if item.find("access_code") is not None
            else None
        )
        if access_code:
            systems = []
            systems_elem = item.find("systems")
            if systems_elem is not None:
                for system in systems_elem.findall("system"):
                    system_info = {
                        "ip": (
                            system.find("ip").text
                            if system.find("ip") is not None
                            else ""
                        ),
                        "system_note": (
                            system.find("system_note").text
                            if system.find("system_note") is not None
                            else ""
                        ),
                    }
                    systems.append(system_info)
            thumbnail_systems[access_code] = systems

    return thumbnail_systems


def get_all_systems(systems_dict: Dict[str, List[str]]) -> List[str]:
    """Get a unique sorted list of all systems across all access codes"""
    all_systems = set()
    for systems in systems_dict.values():
        all_systems.update(systems)
    return sorted(list(all_systems))


def get_access_codes_from_xml(xml_file: str) -> List[str]:
    """Extract all access codes from an XML file"""
    tree = ET.parse(xml_file)
    root = tree.getroot()
    access_codes = []

    # Check if it's group config
    for student in root.findall(".//student"):
        access_code = student.find("access_code")
        if access_code is not None and access_code.text:
            access_codes.append(access_code.text)

    # Check if it's thumbnail settings
    for item in root.findall(".//thumbnail_item"):
        access_code = item.find("access_code")
        if access_code is not None and access_code.text:
            access_codes.append(access_code.text)

    return sorted(list(set(access_codes)))


def save_to_archive(files):
    """Save uploaded files to archive with metadata"""
    # Load existing metadata
    metadata_path = os.path.join(ARCHIVE_FOLDER, ARCHIVE_METADATA)
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
    else:
        metadata = []

    # Create archive entry
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_entry = {
        "id": timestamp,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "zip_filename": f"{timestamp}_config_files.zip",
        "files": {},
    }

    # Create zip file
    zip_path = os.path.join(ARCHIVE_FOLDER, archive_entry["zip_filename"])
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Process each file
        for file_key, file in files.items():
            if file and file.filename:
                # Save file content to BytesIO for processing
                file_content = BytesIO(file.read())

                # Extract access codes
                file_content.seek(0)
                access_codes = get_access_codes_from_xml(file_content)

                # Add file to zip
                file_content.seek(0)
                original_name = secure_filename(file.filename)
                zipf.writestr(original_name, file_content.read())

                # Add to entry
                archive_entry["files"][file_key] = {
                    "original_name": original_name,
                    "access_codes": access_codes,
                }

                # Reset file pointer for later use
                file.seek(0)

    # Add entry to metadata
    metadata.append(archive_entry)

    # Save metadata
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    return archive_entry


def save_new_config(original_files, modified_files):
    """Save newly generated config files"""
    # Load existing metadata
    metadata_path = os.path.join(NEW_CONFIGS_FOLDER, NEW_CONFIGS_METADATA)
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
    else:
        metadata = []

    # Create new config entry
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    config_entry = {
        "id": timestamp,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "zip_filename": f"{timestamp}_new_config_files.zip",
        "files": {},
        "based_on": {},
    }

    # Create zip file for the new configs
    zip_path = os.path.join(NEW_CONFIGS_FOLDER, config_entry["zip_filename"])
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Add modified files to zip
        for file_key, file_path in modified_files.items():
            if os.path.exists(file_path):
                # Read the modified file
                with open(file_path, "rb") as f:
                    file_content = BytesIO(f.read())

                # Extract access codes
                file_content.seek(0)
                access_codes = get_access_codes_from_xml(file_content)

                # Add to zip
                original_name = os.path.basename(file_path)
                zipf.write(file_path, original_name)

                # Add to entry
                config_entry["files"][file_key] = {
                    "original_name": original_name,
                    "access_codes": access_codes,
                }

        # Store information about original files
        for file_key, file in original_files.items():
            if file and file.filename:
                config_entry["based_on"][file_key] = secure_filename(file.filename)

    # Add entry to metadata
    metadata.append(config_entry)

    # Save metadata
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    return config_entry


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        # Check if both files are present
        if "file1" not in request.files or "file2" not in request.files:
            flash("Both files are required")
            return redirect(request.url)

        file1 = request.files["file1"]
        file2 = request.files["file2"]

        # Validate each file
        if not validate_file(file1, REQUIRED_FILES["file1"]):
            flash(f"First file must be named {REQUIRED_FILES['file1']}")
            return redirect(request.url)

        if not validate_file(file2, REQUIRED_FILES["file2"]):
            flash(f"Second file must be named {REQUIRED_FILES['file2']}")
            return redirect(request.url)

        # Clear all previous state from session
        session.clear()

        # Process IP list if enabled
        use_ip_list = request.form.get("useIpList") == "on"
        ip_text = request.form.get("ipList", "").strip()

        # Store form data in session
        session["use_ip_list"] = use_ip_list
        session["ip_list_text"] = ip_text

        # Process IP list
        ip_list = []
        if use_ip_list and ip_text:
            ip_list = [ip.strip() for ip in ip_text.split("\n") if ip.strip()]
        session["ip_list"] = ip_list

        # Save to archive first
        archive_entry = save_to_archive({"file1": file1, "file2": file2})

        # Reset file pointers
        file1.seek(0)
        file2.seek(0)

        # Save the files to upload folder
        file1.save(os.path.join(app.config["UPLOAD_FOLDER"], REQUIRED_FILES["file1"]))
        file2.save(os.path.join(app.config["UPLOAD_FOLDER"], REQUIRED_FILES["file2"]))

        flash("Files uploaded successfully and archived")
        return redirect(url_for("edit_group_config"))

    # On GET, restore previous state if it exists
    use_ip_list = session.get("use_ip_list", False)
    ip_list_text = session.get("ip_list_text", "")

    return render_template(
        "upload.html", use_ip_list=use_ip_list, ip_list_text=ip_list_text
    )


def write_xml_file(tree: ET.ElementTree, filepath: str):
    """Write XML file with correct formatting"""
    # Register namespace to avoid ns0 prefix
    ET.register_namespace("", "")

    # Convert to string with proper formatting
    xml_str = '<?xml version="1.1" encoding="UTF-8" standalone="no" ?>\n'
    # Remove xml declaration since we're adding our own
    xml_content = ET.tostring(
        tree.getroot(),
        encoding="unicode",
        method="xml",
        xml_declaration=False,
        short_empty_elements=False,
    )

    # Write to file
    with open(filepath, "w", encoding="UTF-8") as f:
        f.write(xml_str + xml_content)


@app.route("/edit/group-config", methods=["GET", "POST"])
def edit_group_config():
    student_systems = parse_group_config()
    if not student_systems:
        flash("Please upload group_config.xml first")
        return redirect(url_for("upload"))

    # Get IP list from session
    use_ip_list = session.get("use_ip_list", False)
    ip_list = session.get("ip_list", [])

    if request.method == "POST":
        # Store the checked systems in session
        checked_systems = {}
        for access_code in student_systems.keys():
            systems = request.form.getlist(f"systems_{access_code}")
            checked_systems[access_code] = systems
        session["group_config_checked"] = checked_systems

        # Process form data and create new XML
        new_systems = {}
        for access_code in student_systems.keys():
            systems = request.form.getlist(f"systems_{access_code}")
            new_systems[access_code] = systems

        # Create new XML file
        tree = ET.parse(
            os.path.join(app.config["UPLOAD_FOLDER"], REQUIRED_FILES["file1"])
        )
        root = tree.getroot()

        # Process each group
        groups = list(root.findall("group"))
        # Sort groups by group_id to maintain order (Instructor -> Unassigned -> Pending)
        groups.sort(
            key=lambda g: (
                int(g.find("group_id").text)
                if g.find("group_id") is not None
                and g.find("group_id").text is not None
                else 0
            )
        )

        # Remove all groups from root
        for group in groups:
            root.remove(group)

        # Process groups in order
        for group in groups:
            students = group.find("students")
            if students is not None:
                # Get all students and sort them
                student_list = list(students.findall("student"))
                # Remove all students from XML
                for student in student_list:
                    students.remove(student)
                # Sort students by access code suffix
                student_list.sort(
                    key=lambda s: (
                        s.find("access_code").text[-2:]
                        if s.find("access_code") is not None
                        and s.find("access_code").text is not None
                        else ""
                    )
                )
                # Add students back in sorted order
                for student in student_list:
                    students.append(student)
                    access_code = (
                        student.find("access_code").text
                        if student.find("access_code") is not None
                        else None
                    )
                    if access_code in new_systems:
                        systems_parent = student.find("systems")
                        if systems_parent is not None:
                            # Get all current systems
                            current_systems = systems_parent.findall("system")
                            # Remove systems not in the new list
                            for system in list(
                                current_systems
                            ):  # Use list() to avoid modification during iteration
                                system_name = (
                                    system.find("name").text
                                    if system.find("name") is not None
                                    else None
                                )
                                if system_name not in new_systems[access_code]:
                                    systems_parent.remove(system)
            # Add the processed group back to root
            root.append(group)

        # Save modified XML using custom writer
        output_path = os.path.join(NEW_CONFIGS_FOLDER, f"new_{REQUIRED_FILES['file1']}")
        write_xml_file(tree, output_path)

        # Save to new configs archive
        config_entry = save_new_config(
            original_files={"file1": request.files.get("file1")},
            modified_files={"file1": output_path},
        )

        flash("New group_config.xml has been generated and saved to New Configurations")
        return render_template(
            "edit_group_config.html",
            student_systems=student_systems,
            use_ip_list=use_ip_list,
            ip_list=ip_list,
            checked_systems=checked_systems,
        )

    # On GET, restore previous state if it exists, otherwise initialize from current systems
    checked_systems = session.get("group_config_checked")
    if checked_systems is None:
        checked_systems = {}
        for access_code, systems in student_systems.items():
            if use_ip_list:
                # Only check systems with IPs in the list
                checked_systems[access_code] = [
                    system["name"] for system in systems if system["ip"] in ip_list
                ]
            else:
                # Check all systems
                checked_systems[access_code] = [system["name"] for system in systems]
        session["group_config_checked"] = checked_systems

    return render_template(
        "edit_group_config.html",
        student_systems=student_systems,
        use_ip_list=use_ip_list,
        ip_list=ip_list,
        checked_systems=checked_systems,
    )


@app.route("/edit/thumbnail-settings", methods=["GET", "POST"])
def edit_thumbnail_settings():
    thumbnail_systems = parse_thumbnail_settings()
    if not thumbnail_systems:
        flash("Please upload thumbnail_settings.xml first")
        return redirect(url_for("upload"))

    # Get IP list from session
    use_ip_list = session.get("use_ip_list", False)
    ip_list = session.get("ip_list", [])

    if request.method == "POST":
        # Store the checked systems in session
        checked_systems = {}
        for access_code in thumbnail_systems.keys():
            systems = request.form.getlist(f"systems_{access_code}")
            checked_systems[access_code] = systems
        session["thumbnail_checked"] = checked_systems

        # Process form data and create new XML
        new_systems = {}
        for access_code in thumbnail_systems.keys():
            systems = request.form.getlist(f"systems_{access_code}")
            new_systems[access_code] = systems

        # Create new XML file
        tree = ET.parse(
            os.path.join(app.config["UPLOAD_FOLDER"], REQUIRED_FILES["file2"])
        )
        root = tree.getroot()

        for item in root.findall(".//thumbnail_item"):
            access_code = (
                item.find("access_code").text
                if item.find("access_code") is not None
                else None
            )
            if access_code in new_systems:
                systems_elem = item.find("systems")
                if systems_elem is not None:
                    # Get all current systems
                    current_systems = systems_elem.findall("system")
                    # Remove systems not in the new list
                    for system in list(
                        current_systems
                    ):  # Use list() to avoid modification during iteration
                        system_ip = (
                            system.find("ip").text
                            if system.find("ip") is not None
                            else None
                        )
                        if system_ip not in new_systems[access_code]:
                            systems_elem.remove(system)

        # Save modified XML using custom writer
        output_path = os.path.join(NEW_CONFIGS_FOLDER, f"new_{REQUIRED_FILES['file2']}")
        write_xml_file(tree, output_path)

        # Save to new configs archive
        config_entry = save_new_config(
            original_files={"file2": request.files.get("file2")},
            modified_files={"file2": output_path},
        )

        flash(
            "New thumbnail_settings.xml has been generated and saved to New Configurations"
        )
        return render_template(
            "edit_thumbnail_settings.html",
            thumbnail_systems=thumbnail_systems,
            use_ip_list=use_ip_list,
            ip_list=ip_list,
            checked_systems=checked_systems,
        )

    # On GET, restore previous state if it exists, otherwise initialize from current systems
    checked_systems = session.get("thumbnail_checked")
    if checked_systems is None:
        checked_systems = {}
        for access_code, systems in thumbnail_systems.items():
            if use_ip_list:
                # Only check systems with IPs in the list
                checked_systems[access_code] = [
                    system["ip"] for system in systems if system["ip"] in ip_list
                ]
            else:
                # Check all systems
                checked_systems[access_code] = [system["ip"] for system in systems]
        session["thumbnail_checked"] = checked_systems

    return render_template(
        "edit_thumbnail_settings.html",
        thumbnail_systems=thumbnail_systems,
        use_ip_list=use_ip_list,
        ip_list=ip_list,
        checked_systems=checked_systems,
    )


@app.route("/archive")
def archive():
    """Display archive of uploaded files"""
    metadata_path = os.path.join(ARCHIVE_FOLDER, ARCHIVE_METADATA)
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
    else:
        metadata = []

    return render_template("archive.html", archives=metadata)


@app.route("/archive/download/<timestamp>")
def download_archive(timestamp):
    """Download a zip file from the archive"""
    # Load metadata
    metadata_path = os.path.join(ARCHIVE_FOLDER, ARCHIVE_METADATA)
    if not os.path.exists(metadata_path):
        flash("Archive not found")
        return redirect(url_for("archive"))

    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Find the archive entry
    archive_entry = next(
        (entry for entry in metadata if entry["id"] == timestamp), None
    )
    if not archive_entry:
        flash("Archive not found")
        return redirect(url_for("archive"))

    zip_path = os.path.join(ARCHIVE_FOLDER, archive_entry["zip_filename"])
    if not os.path.exists(zip_path):
        flash("Archive file not found")
        return redirect(url_for("archive"))

    return send_file(
        zip_path, as_attachment=True, download_name=archive_entry["zip_filename"]
    )


@app.route("/new-configs")
def new_configs():
    """Display new configurations page"""
    metadata_path = os.path.join(NEW_CONFIGS_FOLDER, NEW_CONFIGS_METADATA)
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
    else:
        metadata = []

    return render_template("new_configs.html", configs=metadata)


@app.route("/new-configs/download/<timestamp>")
def download_new_config(timestamp):
    """Download a zip file of new configurations"""
    # Load metadata
    metadata_path = os.path.join(NEW_CONFIGS_FOLDER, NEW_CONFIGS_METADATA)
    if not os.path.exists(metadata_path):
        flash("Configuration not found")
        return redirect(url_for("new_configs"))

    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Find the config entry
    config_entry = next((entry for entry in metadata if entry["id"] == timestamp), None)
    if not config_entry:
        flash("Configuration not found")
        return redirect(url_for("new_configs"))

    zip_path = os.path.join(NEW_CONFIGS_FOLDER, config_entry["zip_filename"])
    if not os.path.exists(zip_path):
        flash("Configuration file not found")
        return redirect(url_for("new_configs"))

    return send_file(
        zip_path, as_attachment=True, download_name=config_entry["zip_filename"]
    )


@app.route("/archive/delete/<timestamp>")
def delete_archive(timestamp):
    """Delete an archive entry and its associated files"""
    # Load metadata
    metadata_path = os.path.join(ARCHIVE_FOLDER, ARCHIVE_METADATA)
    if not os.path.exists(metadata_path):
        flash("Archive not found")
        return redirect(url_for("archive"))

    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Find and remove the archive entry
    archive_entry = next(
        (entry for entry in metadata if entry["id"] == timestamp), None
    )
    if not archive_entry:
        flash("Archive entry not found")
        return redirect(url_for("archive"))

    # Remove the zip file
    zip_path = os.path.join(ARCHIVE_FOLDER, archive_entry["zip_filename"])
    if os.path.exists(zip_path):
        os.remove(zip_path)

    # Remove entry from metadata
    metadata.remove(archive_entry)

    # Save updated metadata
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    flash("Archive entry deleted successfully")
    return redirect(url_for("archive"))


@app.route("/new-configs/delete/<timestamp>")
def delete_new_config(timestamp):
    """Delete a new config entry and its associated files"""
    # Load metadata
    metadata_path = os.path.join(NEW_CONFIGS_FOLDER, NEW_CONFIGS_METADATA)
    if not os.path.exists(metadata_path):
        flash("Configuration not found")
        return redirect(url_for("new_configs"))

    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Find and remove the config entry
    config_entry = next((entry for entry in metadata if entry["id"] == timestamp), None)
    if not config_entry:
        flash("Configuration entry not found")
        return redirect(url_for("new_configs"))

    # Remove the zip file
    zip_path = os.path.join(NEW_CONFIGS_FOLDER, config_entry["zip_filename"])
    if os.path.exists(zip_path):
        os.remove(zip_path)

    # Remove entry from metadata
    metadata.remove(config_entry)

    # Save updated metadata
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    flash("Configuration entry deleted successfully")
    return redirect(url_for("new_configs"))


@app.route("/archive/delete-all")
def delete_all_archives():
    """Delete all archive entries and their associated files"""
    # Load metadata
    metadata_path = os.path.join(ARCHIVE_FOLDER, ARCHIVE_METADATA)
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        # Remove all zip files
        for entry in metadata:
            zip_path = os.path.join(ARCHIVE_FOLDER, entry["zip_filename"])
            if os.path.exists(zip_path):
                os.remove(zip_path)

        # Clear metadata
        with open(metadata_path, "w") as f:
            json.dump([], f, indent=2)

    flash("All archive entries have been deleted")
    return redirect(url_for("archive"))


@app.route("/new-configs/delete-all")
def delete_all_new_configs():
    """Delete all new config entries and their associated files"""
    # Load metadata
    metadata_path = os.path.join(NEW_CONFIGS_FOLDER, NEW_CONFIGS_METADATA)
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        # Remove all zip files
        for entry in metadata:
            zip_path = os.path.join(NEW_CONFIGS_FOLDER, entry["zip_filename"])
            if os.path.exists(zip_path):
                os.remove(zip_path)

        # Clear metadata
        with open(metadata_path, "w") as f:
            json.dump([], f, indent=2)

    flash("All configuration entries have been deleted")
    return redirect(url_for("new_configs"))


@app.route("/update-checkbox-state", methods=["POST"])
def update_checkbox_state():
    """Update the session state when checkboxes are changed"""
    data = request.get_json()
    page_type = data.get("page_type")
    access_code = data.get("access_code")
    system_id = data.get("system_id")
    is_checked = data.get("is_checked")

    if page_type == "group_config":
        # Initialize if not exists
        if "group_config_checked" not in session:
            session["group_config_checked"] = {}
        if access_code not in session["group_config_checked"]:
            session["group_config_checked"][access_code] = []

        # Update the list
        checked_systems = session["group_config_checked"][access_code]
        if is_checked and system_id not in checked_systems:
            checked_systems.append(system_id)
        elif not is_checked and system_id in checked_systems:
            checked_systems.remove(system_id)
        session["group_config_checked"][access_code] = checked_systems
        session.modified = True

    elif page_type == "thumbnail":
        # Initialize if not exists
        if "thumbnail_checked" not in session:
            session["thumbnail_checked"] = {}
        if access_code not in session["thumbnail_checked"]:
            session["thumbnail_checked"][access_code] = []

        # Update the list
        checked_systems = session["thumbnail_checked"][access_code]
        if is_checked and system_id not in checked_systems:
            checked_systems.append(system_id)
        elif not is_checked and system_id in checked_systems:
            checked_systems.remove(system_id)
        session["thumbnail_checked"][access_code] = checked_systems
        session.modified = True

    return {"status": "success"}


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
