import streamlit as st
import subprocess
import pandas as pd
from pathlib import Path
import shutil
import sys
import time
import os

st.set_page_config(page_title="CFU Counter", layout="wide")

st.title("🧫 CFU Counter")
st.write("Upload TIF images or specify a folder to count colonies using Cellpose.")

# Sidebar for controls
st.sidebar.header("Configuration")
mode = st.sidebar.radio("Input Source", ["Upload Images", "Local Folder Path"])

import uuid

# ...
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# Unique directories per session/run
base_temp = Path("temp_data")
base_temp.mkdir(exist_ok=True)

# We'll create specific run dirs dynamically, 
# but initialized to None here
target_dir = None
result_dir = None
run_clicked = False

if mode == "Upload Images":
    st.subheader("Upload Images")
    uploaded_files = st.file_uploader(
        "Drop TIF/TIFF/PNG/JPG images here", 
        accept_multiple_files=True,
        type=["tif", "tiff", "png", "jpg", "jpeg"]
    )
    
    if uploaded_files:
        # Create unique temp directory for this upload batch
        batch_id = str(uuid.uuid4())[:8]
        temp_dir = base_temp / f"upload_{st.session_state.session_id}_{batch_id}"
        if temp_dir.exists():
             shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Save files
        for uploaded_file in uploaded_files:
            file_path = temp_dir / uploaded_file.name
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
        
        target_dir = temp_dir.absolute()
        st.success(f"Prepared {len(uploaded_files)} images in temporary folder.")
        
        run_clicked = st.button("Run Counting")

elif mode == "Local Folder Path":
    st.subheader("Local Folder")
    folder_path = st.text_input("Enter absolute path to folder containing images:")
    if folder_path:
        target_dir = Path(folder_path)
        if not target_dir.is_dir():
            st.error("Invalid directory path.")
            target_dir = None
        else:
            st.info(f"Target: {target_dir}")
            run_clicked = st.button(f"Run Counting on {target_dir.name}")

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
def create_zip_of_run(source_dir, run_name):
    """
    Creates a zip archive containing colony_counts.csv and the Images folder.
    Returns the path to the zip file.
    """
    # Create a staging area for the zip content
    staging_dir = source_dir / run_name
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir()

    try:
        # 1. Copy CSV
        csv_source = source_dir / "colony_counts.csv"
        if csv_source.exists():
            shutil.copy(csv_source, staging_dir / "colony_counts.csv")

        # 2. Copy Images
        visuals_source = source_dir / "cp_visuals"
        images_dest = staging_dir / "Images"
        images_dest.mkdir()
        
        if visuals_source.exists():
            for img_file in visuals_source.glob("*"):
                if img_file.is_file() and not img_file.name.startswith("."):
                    shutil.copy(img_file, images_dest / img_file.name)

        # 3. Zip it
        # make_archive works on the content of root_dir
        zip_base_name = source_dir / run_name
        zip_path = shutil.make_archive(
            base_name=str(zip_base_name), 
            format="zip", 
            root_dir=str(source_dir),
            base_dir=run_name
        )
        return zip_path

    except Exception as e:
        st.error(f"Error creating zip: {e}")
        return None
    finally:
        # Cleanup staging dir
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

# State Initialization
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
if "result_dir" not in st.session_state:
    st.session_state.result_dir = None

# ... (Previous code remains, but we need to update state on successful run)

# Start Analysis
if run_clicked and target_dir:
    # Use unique result dir
    run_id = str(uuid.uuid4())[:8]
    result_dir = base_temp / f"results_{st.session_state.session_id}_{run_id}"
    result_dir.mkdir(parents=True, exist_ok=True)
    
    st.session_state.result_dir = result_dir 
    st.divider()
    st.write(f"**Running analysis on:** `{target_dir}`")
    
    # ... (Analysis setup code) ...
    # CRITICAL: Resolve cfu_count.py relative to THIS file (app.py), 
    # not the current working directory.
    script_path = (Path(__file__).parent / "cfu_count.py").absolute()
    if not script_path.exists():
        st.error(f"cfu_count.py not found at {script_path}!")
        st.stop()

    status_text = st.empty()
    status_text.text("Starting analysis process...")
    
    logs_expander = st.expander("Show Logs", expanded=True)
    log_area = logs_expander.empty()
    
    # Use the specific cellpose environment python executable if it exists (Local Mac),
    # otherwise default to the current system python (Streamlit Cloud/GitHub)
    local_cellpose_python = Path("/opt/anaconda3/envs/cellpose/bin/python")
    if local_cellpose_python.exists():
        cellpose_python = str(local_cellpose_python)
    else:
        cellpose_python = sys.executable

    cmd = [cellpose_python, str(script_path), str(target_dir), str(result_dir)]
    
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1
        )
        
        log_content = ""
        while True:
            line = process.stdout.readline()
            # ... (Log reading loop) ...
            if not line and process.poll() is not None:
                break
            if line:
                log_content += line
                status_text.text(f"Running... {line.strip()[:100]}")
                log_area.code(log_content)
        
        if process.returncode == 0:
            status_text.success("Analysis Complete!")
            st.session_state.analysis_done = True
            st.session_state.result_dir = result_dir
        else:
            status_text.error("Script failed.")
            st.error("Process exited with errors.")
            st.session_state.analysis_done = False
            
    except Exception as e:
        st.error(f"Error running subprocess: {e}")
        st.session_state.analysis_done = False

# -----------------------------------------------------------------------------
# Results Display (Based on Session State)
# -----------------------------------------------------------------------------
if st.session_state.analysis_done and st.session_state.result_dir:
    res_dir = st.session_state.result_dir
    
    # 1. Display CSV
    csv_path = res_dir / "colony_counts.csv"
    if csv_path.exists():
        st.subheader("📊 Colony Counts")
        df = pd.read_csv(csv_path)
        st.dataframe(df)
    else:
        st.warning("No CSV output found.")
    
    # 2. Display Overlays
    visuals_dir = res_dir / "cp_visuals"
    if visuals_dir.exists():
        st.subheader("🖼️ Overlays")
        images = sorted(list(visuals_dir.glob("*_overlay.png")))
        if images:
            cols = st.columns(3)
            for idx, img_path in enumerate(images):
                with cols[idx % 3]:
                    st.image(str(img_path), caption=img_path.name, use_container_width=True)
        else:
            st.warning("No overlay images found.")

    # 3. Save Section
    st.divider()
    st.write("### Save Results")
    
    run_name = st.text_input("Name your run (folder name):", value="CFU_Run_Results")
    
    # Only generate zip if we are ready to display the button
    # but st.download_button logic requires the file/data to be present.
    # We call create_zip_of_run every rerun? Efficient enough for small files.
    
    zip_path = create_zip_of_run(res_dir, run_name)
    
    if zip_path:
        with open(zip_path, "rb") as f:
            st.download_button(
                label="📁 Save Run (Download Zip)",
                data=f,
                file_name=f"{run_name}.zip",
                mime="application/zip",
                type="primary"
            )
