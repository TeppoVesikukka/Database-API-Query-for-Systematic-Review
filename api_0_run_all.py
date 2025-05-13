import sys
import threading
import time
import json
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QPushButton,
                             QTextEdit, QLabel, QCheckBox, QProgressBar, QWidget,
                             QLineEdit, QHBoxLayout)
from PyQt5.QtCore import pyqtSlot, Qt, QMetaObject, Q_ARG
from PyQt5.QtCore import QMutex, QMutexLocker, pyqtSignal, QObject

from api_1_ieee import IEEEAPI
from api_2_springer import SpringerAPI
from api_3_scopus import ScopusAPI
from api_4_pubmed import PubMedAPI


# Logger class is used to emit log messages from different threads safely
class Logger(QObject):
    # Define a signal to emit log messages
    log_signal = pyqtSignal(str)


# APIWorker class handles the execution of API requests in a separate thread
class APIWorker(threading.Thread):

    def __init__(self, api_class, initial_terms, secondary_terms, api_key, insttoken, progress_callback, log_callback,
                 save_terms_callback):
        """
        Initializes the APIWorker thread.

        Parameters:
        - api_class: The API class to be instantiated (e.g., IEEEAPI, SpringerAPI).
        - initial_terms: The primary search terms.
        - secondary_terms: The secondary search terms.
        - api_key: The API key for authentication.
        - insttoken: Institution token (used specifically for Scopus API).
        - progress_callback: Function to update the progress bar in the GUI.
        - log_callback: Function to log messages to the GUI.
        - save_terms_callback: Function to save searched terms.
        """
        super().__init__()
        # Instantiate the API class with the provided API key and optionally institution token
        if api_class == ScopusAPI:
            self.api_instance = api_class(api_key, insttoken)
        else:
            self.api_instance = api_class(api_key)
        self.initial_terms = initial_terms
        self.secondary_terms = secondary_terms
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.save_terms_callback = save_terms_callback
        self.request_log = ""  # Will store all the request URLs made by this thread
        self._stop_event = threading.Event()  # Event to signal stopping the thread

    def run(self):
        """Executes the API search and handles logging and progress updates."""
        try:
            # Perform the search using the provided terms
            self.api_instance.search(self.initial_terms, self.secondary_terms, self.log_callback,
                                     self.progress_callback)
            # Save the log of requests made during the search
            self.request_log = self.api_instance.request_log

            # Save each initial and secondary term using the callback
            for term in self.initial_terms + self.secondary_terms:
                self.save_terms_callback(term)
        except Exception as e:
            # Log any error that occurs during the API request
            self.log_callback(f"Error in API: {e}")
            self._stop_event.set()  # Stop the thread if an error occurs

    def stop(self):
        """Sets the stop event to halt the thread."""
        self._stop_event.set()


# MainWindow class defines the main GUI for the Multi-API Search Tool
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-API Search Tool")  # Set the window title
        self.setGeometry(100, 100, 800, 600)  # Set the window size and position
        self.log_mutex = QMutex()  # Mutex to ensure thread-safe logging

        self.logger = Logger()  # Create a Logger instance
        self.logger.log_signal.connect(self.append_log)  # Connect the log signal to the append_log slot

        self.api_keys = self.load_api_keys()  # Load saved API keys from a file

        self.central_widget = QWidget()  # Create the central widget
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout(self.central_widget)  # Set the layout for the central widget

        self.api_checkboxes = {}  # Dictionary to store checkboxes for each API
        self.api_key_inputs = {}  # Dictionary to store input fields for each API key
        self.insttoken_input = None  # Placeholder for the institution token input

        # Add sections for each API with corresponding input fields
        self.add_api_section("IEEE API", "ieee_api_key")
        self.add_api_section("Springer API", "springer_api_key")
        self.add_api_section("Scopus API", "scopus_api_key", include_insttoken=True)
        self.add_api_section("PubMed API", "pubmed_api_key")

        # Text edit fields for entering initial and secondary search terms
        self.initial_terms_text = QTextEdit()
        self.initial_terms_text.setPlaceholderText("Enter initial terms here...")
        self.secondary_terms_text = QTextEdit()
        self.secondary_terms_text.setPlaceholderText("Enter secondary terms here...")

        # Load saved search terms
        self.load_search_terms()

        # Add the text edit fields to the layout
        self.layout.addWidget(QLabel("Initial Terms:"))
        self.layout.addWidget(self.initial_terms_text)
        self.layout.addWidget(QLabel("Secondary Terms:"))
        self.layout.addWidget(self.secondary_terms_text)

        self.progress_bar = QProgressBar()  # Progress bar to show search progress
        self.layout.addWidget(self.progress_bar)

        self.terminal_output = QTextEdit()  # Terminal output to display logs
        self.terminal_output.setReadOnly(True)  # Make the terminal output read-only
        self.layout.addWidget(self.terminal_output)

        # Buttons to start and stop the search
        self.start_button = QPushButton("Start Search")
        self.stop_button = QPushButton("Stop Search")

        # Add the buttons to the layout
        self.layout.addWidget(self.start_button)
        self.layout.addWidget(self.stop_button)

        # Connect buttons to their respective slots
        self.start_button.clicked.connect(self.start_search)
        self.stop_button.clicked.connect(self.stop_search)

        self.api_threads = []  # List to store active API worker threads
        self.searched_terms = []  # List to store terms that have been searched

    def add_api_section(self, api_name, key_name, include_insttoken=False):
        """
        Adds a section in the GUI for an API, including a checkbox, API key input, and optionally an institution token.

        Parameters:
        - api_name: Name of the API (e.g., "IEEE API").
        - key_name: The key used to retrieve and save the API key.
        - include_insttoken: Boolean indicating whether to include an institution token input.
        """
        h_layout = QHBoxLayout()  # Create a horizontal layout for the API section
        checkbox = QCheckBox(api_name)  # Checkbox to enable or disable this API
        self.api_checkboxes[api_name] = checkbox  # Store the checkbox in the dictionary
        h_layout.addWidget(checkbox)

        api_key_input = QLineEdit()  # Input field for the API key
        api_key_input.setPlaceholderText("Enter API key...")
        api_key_input.setText(self.api_keys.get(key_name, ""))  # Load the saved API key if available
        self.api_key_inputs[api_name] = api_key_input  # Store the input field in the dictionary
        h_layout.addWidget(api_key_input)

        if include_insttoken:
            insttoken_input = QLineEdit()  # Input field for the institution token (only for Scopus)
            insttoken_input.setPlaceholderText("Enter InstToken...")
            insttoken_input.setText(self.api_keys.get("scopus_insttoken", ""))
            self.insttoken_input = insttoken_input  # Store the institution token input field
            h_layout.addWidget(insttoken_input)

        self.layout.addLayout(h_layout)  # Add the horizontal layout to the main layout

    def load_api_keys(self):
        """Loads saved API keys from a JSON file."""
        if os.path.exists('api_keys.json'):
            with open('api_keys.json', 'r') as file:
                return json.load(file)  # Load and return the API keys as a dictionary
        return {}

    def save_api_keys(self):
        """Saves the current API keys to a JSON file."""
        api_keys = {
            'ieee_api_key': self.api_key_inputs["IEEE API"].text(),
            'springer_api_key': self.api_key_inputs["Springer API"].text(),
            'scopus_api_key': self.api_key_inputs["Scopus API"].text(),
            'pubmed_api_key': self.api_key_inputs["PubMed API"].text(),
            'scopus_insttoken': self.insttoken_input.text() if self.insttoken_input else ""
        }
        with open('api_keys.json', 'w') as file:
            json.dump(api_keys, file)  # Save the API keys to the JSON file

    def load_search_terms(self):
        """Loads the initial and secondary terms from a JSON file."""
        if os.path.exists('search_terms.json'):
            with open('search_terms.json', 'r') as f:
                search_terms = json.load(f)
                initial_terms = '\n'.join(search_terms.get('initial_terms', []))
                secondary_terms = '\n'.join(search_terms.get('secondary_terms', []))
                self.initial_terms_text.setPlainText(initial_terms)
                self.secondary_terms_text.setPlainText(secondary_terms)

    def save_search_terms(self):
        """Saves the initial and secondary terms to a JSON file."""
        initial_terms = self.initial_terms_text.toPlainText().splitlines()
        secondary_terms = self.secondary_terms_text.toPlainText().splitlines()

        search_terms = {
            'initial_terms': initial_terms,
            'secondary_terms': secondary_terms
        }

        with open('search_terms.json', 'w') as f:
            json.dump(search_terms, f, indent=4)

        self.log_callback("Initial and secondary terms have been saved to 'search_terms.json'.")

    @pyqtSlot()
    def start_search(self):
        """Starts the search process across selected APIs."""
        self.api_threads = []  # Clear any existing threads
        self.save_api_keys()  # Save API keys before starting the search

        # Save the initial and secondary terms
        self.save_search_terms()

        # Check which APIs are selected and start a worker thread for each
        if self.api_checkboxes["IEEE API"].isChecked():
            print("*** IEEE started ***")
            self.run_api("IEEE API", IEEEAPI, self.api_key_inputs["IEEE API"].text())
        if self.api_checkboxes["Springer API"].isChecked():
            print("*** Springer started ***")
            self.run_api("Springer API", SpringerAPI, self.api_key_inputs["Springer API"].text())
        if self.api_checkboxes["Scopus API"].isChecked():
            print("*** Scopus started ***")
            self.run_api("Scopus API", ScopusAPI, self.api_key_inputs["Scopus API"].text(), self.insttoken_input.text())
        if self.api_checkboxes["PubMed API"].isChecked():
            print("*** PubMed started ***")
            self.run_api("PubMed API", PubMedAPI, self.api_key_inputs["PubMed API"].text())

        # self.log_callback("*** Search started.***")  # Log that the search has started

        for thread in self.api_threads:
            thread.join()  # Wait for all threads to finish

        self.save_searched_terms()
        print("*** Terms saved ***")  # Save the searched terms to a file

        self.combine_and_save_logs()
        print("*** Logs combined and saved ***")  # Combine and save the logs from all threads

        self.log_callback("*** All APIs have completed. Search stopped. ***")  # Log that the search has stopped

    def run_api(self, api_name, api_class, api_key, insttoken=None):
        """
        Starts a new API worker thread for the given API.

        Parameters:
        - api_name: The name of the API (used for logging).
        - api_class: The API class to instantiate.
        - api_key: The API key for authentication.
        - insttoken: Optional institution token (only for Scopus).
        """
        # Retrieve the search terms from the text fields
        initial_terms = self.initial_terms_text.toPlainText().splitlines()
        secondary_terms = self.secondary_terms_text.toPlainText().splitlines()

        self.log_callback(f"Starting... {api_name}...")
        print(f"*** Starting... {api_name}... ***")  # Log the start of the API search

        # Create an APIWorker thread to handle the API requests
        if api_class == ScopusAPI:
            api_thread = APIWorker(api_class, initial_terms, secondary_terms, api_key, insttoken, self.update_progress,
                                   self.log_callback, self.save_searched_term)
        else:
            api_thread = APIWorker(api_class, initial_terms, secondary_terms, api_key, None, self.update_progress,
                                   self.log_callback, self.save_searched_term)

        self.api_threads.append(api_thread)  # Add the thread to the list of threads
        api_thread.start()  # Start the thread

    def combine_and_save_logs(self):
        """Combines logs from all API worker threads and saves them to a file."""
        combined_log = ""
        for thread in self.api_threads:
            combined_log += thread.request_log + "\n"  # Append each thread's log to the combined log

        with open("combined_api_requests.log", "w") as log_file:
            log_file.write(combined_log)  # Save the combined log to a file

        self.log_callback("All request URLs have been combined into 'combined_api_requests.log'")  # Log completion

    @pyqtSlot()
    def stop_search(self):
        """Stops all running API worker threads."""
        for thread in self.api_threads:
            thread.stop()  # Signal each thread to stop
        self.api_threads = []  # Clear the list of threads
        self.log_callback("Search stopped manually.")  # Log that the search was stopped manually

    def update_progress(self, value):
        """Updates the progress bar in the GUI."""
        self.progress_bar.setValue(value)

    def log_callback(self, message):
        """Logs a message to the GUI terminal output."""
        self.logger.log_signal.emit(message)

    @pyqtSlot(str)
    def append_log(self, message):
        """Appends a log message to the terminal output."""
        self.terminal_output.append(message)

    def save_searched_term(self, term):
        """Saves a searched term to the list of searched terms."""
        if term not in self.searched_terms:
            self.searched_terms.append(term)

    def save_searched_terms(self):
        """Saves the searched terms to a text file."""
        filename = "searched_terms.txt"
        with open(filename, "w") as file:
            for term in self.searched_terms:
                file.write(term + "\n")  # Write each searched term on a new line
        self.log_callback(f"Searched terms saved to '{filename}'")  # Log that the terms have been saved

    def closeEvent(self, event):
        """Handles the event when the window is closed."""
        self.save_searched_terms()  # Save the searched terms before closing
        self.save_api_keys()  # Save the API keys before closing
        self.save_search_terms()  # Save the search terms before closing
        event.accept()  # Accept the close event


# Entry point of the program
if __name__ == "__main__":
    app = QApplication(sys.argv)  # Create the application object
    main_window = MainWindow()  # Create the main window
    main_window.show()  # Show the main window
    sys.exit(app.exec_())  # Run the application event loop
