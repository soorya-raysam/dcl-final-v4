from flask import Flask, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    try:
        base_path = "/Users/sooryaraysam/Checklist Automation"

        # Run the first notebook: gui_final_auto.ipynb
        result1 = subprocess.run([
            "jupyter", "nbconvert", "--to", "notebook", "--execute",
            "--inplace", os.path.join(base_path, "gui_final_auto.ipynb")
        ], capture_output=True, text=True)

        if result1.returncode != 0:
            return jsonify({"error": "gui_final_auto failed", "details": result1.stderr}), 500

        # Then run the second notebook
        result2 = subprocess.run([
            "jupyter", "nbconvert", "--to", "notebook", "--execute",
            "--inplace", os.path.join(base_path, "generate_health_snapshot.ipynb")
        ], capture_output=True, text=True)

        if result2.returncode != 0:
            return jsonify({"error": "generate_health_snapshot failed", "details": result2.stderr}), 500

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5002, debug=True)
