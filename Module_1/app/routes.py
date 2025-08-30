from flask import Blueprint, render_template

bp = Blueprint('main', __name__)

@bp.route('/')
def home():
    return render_template("home.html", active_tab="home")

@bp.route("/contact")
def contact():
    return render_template("contact.html", active_tab="contact")

@bp.route("/projects")
def projects():
    module_1 = {
        "github_url": "https://github.com/Jhawes-jr/jhu_software_concepts.git"
    }
    return render_template("projects.html", module_1=module_1,  active_tab="projects")