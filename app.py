import os
import re
import threading
import traceback
import uuid
import csv
from flask import Flask, jsonify, redirect, render_template, request, url_for

from config import Config
from process import TASKS_STATUS, initiate_task, save_uuid_to_file, verify_seller

app = Flask(__name__)
app.config.from_object(Config)


@app.route("/", methods=["POST", "GET"])
def index():
    if request.method == "POST":
        unique_id = str(uuid.uuid4())
        TASKS_STATUS[unique_id] = {"completed": False}

        # Get the genre and style values
        genre = request.form.get("genre", "").strip()
        style = request.form.get("style", "").strip()

        form_data = {
            "user_input": request.form.get("user_input"),
            "vinyls": "",  # Initialize empty
            "genre": "",   # Initialize empty
            "style": "",   # Initialize empty
        }
        
        # Only add parameters if they are provided
        if request.form.get("vinyls_only") == "on":
            form_data["vinyls"] = "&format=Vinyl"
        if genre:
            form_data["genre"] = f"&genre={genre}"
        if style:
            form_data["style"] = f"&style={style}"

        print(f"Form data: {form_data}")  # Debug print
        is_seller = verify_seller(form_data["user_input"])

        if not is_seller:
            return jsonify(
                success=False,
                message="This seller does not exist or does not offer any records for sale",
            )
        else:
            threading.Thread(
                target=initiate_task, args=(form_data, app, unique_id)
            ).start()
            return jsonify(
                success=True,
                message="Getting data... (May take up to a minute)",
                unique_id=unique_id,
            )
    return render_template("index.html")


@app.route("/task_status/<unique_id>")
def task_status(unique_id):
    if unique_id not in TASKS_STATUS:
        return jsonify(error="Invalid task id", completed=None), 404
    return jsonify(completed=TASKS_STATUS[unique_id]["completed"])


@app.route("/table/")
def render_table():
    unique_id = str(uuid.uuid4())
    save_uuid_to_file(unique_id)
    return redirect(url_for("render_table_with_id", unique_id=unique_id))


@app.route("/table/<unique_id>")
def render_table_with_id(unique_id):
    file_path = f"data/pages/{unique_id}.csv"
    if not os.path.exists(file_path):
        return "Seller's collection with this ID does not exist", 404
    return render_template("table.html", unique_id=unique_id)


@app.route("/serve_table_data/<unique_id>")
def serve_table_data(unique_id):
    try:
        if not os.path.exists(f"data/pages/{unique_id}.csv"):
            return jsonify({"error": "File not found"})

        # Read CSV file
        data = []
        with open(f"data/pages/{unique_id}.csv", 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            data = list(reader)

        # Sort data if requested
        order_column = request.args.get('order[0][column]')
        order_dir = request.args.get('order[0][dir]')
        if order_column and order_dir:
            # Get the column name from the index
            columns = ['title', 'price', 'condition', 'format', 'year']  # Add all your column names
            sort_col = columns[int(order_column)]
            reverse = order_dir == 'desc'
            data.sort(key=lambda x: x[sort_col], reverse=reverse)

        # Apply search if provided
        search = request.args.get('search[value]')
        if search:
            search = search.lower()
            filtered_data = []
            for row in data:
                if any(search in str(val).lower() for val in row.values()):
                    filtered_data.append(row)
            data = filtered_data

        # Get pagination parameters
        start = int(request.args.get('start', 0))
        length = int(request.args.get('length', 10))

        # Paginate the results
        paginated_data = data[start:start + length]

        response_data = {
            "draw": int(request.args.get('draw', 1)),
            "recordsTotal": len(data),
            "recordsFiltered": len(data),
            "data": paginated_data,
        }

        print("\nResponse summary:")
        print(f"- Total records: {response_data['recordsTotal']}")
        print(f"- Filtered records: {response_data['recordsFiltered']}")
        print(f"- Records in this page: {len(response_data['data'])}")

        return jsonify(response_data)

    except Exception as e:
        print(f"Error in serve_table_data: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)})


if __name__ == "__main__":
    if os.environ.get("VERCEL") is None:
        app.run(debug=True)
