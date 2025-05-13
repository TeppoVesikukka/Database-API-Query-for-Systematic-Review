import requests
import json
import time
import os

class SpringerAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.springernature.com"
        self.api_path = "/openaccess/json"
        self.max_requests_per_day = 500
        self.request_counter = 0
        self.start_time = time.time()
        self.checkpoint_file = 'checkpoint_springer.json'
        self.all_results = {}
        self.total_saved_records = 0
        self.request_log = ""  # Initialize request_log

        # Load checkpoint if exists
        checkpoint_data = self.load_checkpoint()
        if checkpoint_data:
            self.all_results = checkpoint_data['all_results']
            self.total_saved_records = checkpoint_data['total_saved_records']
            self.item_index = checkpoint_data['item_index']
            self.keyword_index = checkpoint_data['keyword_index']
            self.name_index = checkpoint_data['name_index']
            # Restore request_counter and request_log
            self.request_counter = checkpoint_data.get('request_counter', 0)
            self.request_log = checkpoint_data.get('request_log', "")
        else:
            self.item_index = 0
            self.keyword_index = 0
            self.name_index = 0
            self.request_log = ""  # Reset request_log
            self.request_counter = 0  # Reset request_counter

    def load_checkpoint(self):
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file, 'r') as f:
                data = json.load(f)
                self.request_counter = data.get('request_counter', 0)
                self.request_log = data.get('request_log', "")
                return data
        return None

    def save_checkpoint(self, data):
        data['request_counter'] = self.request_counter
        data['request_log'] = self.request_log
        with open(self.checkpoint_file, 'w') as f:
            json.dump(data, f)

    def get_data_from_url(self, url, log_callback):
        if self.request_counter >= self.max_requests_per_day:
            log_callback(f"Springer API reached {self.max_requests_per_day} requests. Pausing for 24 hours.")
            print(f"Springer API reached {self.max_requests_per_day} requests. Pausing for 24 hours.")
            time.sleep(24 * 60 * 60)  # Sleep for 24 hours
            self.request_counter = 0  # Reset the counter after sleep
        self.request_log += f"Springer API request #{self.request_counter + 1}: {url}\n"  # Log the request URL
        response = requests.get(url)
        data = response.json()
        self.request_counter += 1
        return data

    def extract_data(self, data):
        return [
            {
                "title": record.get("title", "null"),
                "abstract": record.get("abstract", "null"),
                "authors": ', '.join([author.get("creator", "null") for author in record.get("creators", [])]),
                "doi": record.get("doi", "No DOI"),
                "isbn": record.get("isbn", "null"),
                "issn": record.get("issn", "null"),
                "publicationDate": record.get("publicationDate", "null")
            }
            for record in data.get("records", [])
        ]

    def search(self, initial_terms, secondary_terms, log_callback, progress_callback):
        for i in range(self.item_index, len(initial_terms)):
            item = initial_terms[i]
            bias_names = item.split(" or ")
            if len(bias_names) == 1:
                if item not in self.all_results:
                    bias_results = {"Total records": 0, "Records": {kw: [] for kw in secondary_terms}}
                    self.all_results[item] = bias_results
                for j in range(self.keyword_index, len(secondary_terms)):
                    keyword = secondary_terms[j]
                    query = f'("{bias_names[0].strip()}" AND "{keyword}")'
                    initial_url = f"{self.base_url}{self.api_path}?q={query}&api_key={self.api_key}"
                    item_results = []
                    current_url = initial_url
                    request_for_item = 1
                    total_records = 0  # Initialize total_records

                    while current_url:
                        time.sleep(1)
                        data = self.get_data_from_url(current_url, log_callback)
                        elapsed_time = time.time() - self.start_time
                        log_callback(f"Springer API request {self.request_counter} made at {elapsed_time:.2f} seconds.")
                        print(f"Springer API request {self.request_counter} made at {elapsed_time:.2f} seconds.")
                        if not data:
                            break

                        if total_records == 0:
                            total_records = int(data["result"][0]["total"])
                            total_requests_for_item = -(-total_records // 100)

                        item_results.extend(self.extract_data(data))
                        current_url = data.get("nextPage", None)
                        if current_url:
                            current_url = self.base_url + current_url
                        else:
                            current_url = None  # Explicitly set to None to end the loop
                        request_for_item += 1
                        progress_callback(self.request_counter)

                    self.all_results[item]["Records"][keyword] = item_results
                    self.all_results[item]["Total records"] += len(item_results)
                    self.total_saved_records += len(item_results)

                    checkpoint_data = {
                        'all_results': self.all_results,
                        'total_saved_records': self.total_saved_records,
                        'item_index': i,
                        'keyword_index': j + 1,
                        'name_index': 0,
                        'request_counter': self.request_counter,
                        'request_log': self.request_log
                    }
                    self.save_checkpoint(checkpoint_data)

            else:
                if item not in self.all_results:
                    bias_results = {"Total records": 0,
                                    "Records": {
                                        name: {"Total records": 0, "Records": {kw: [] for kw in secondary_terms}}
                                        for name in bias_names}}
                    self.all_results[item] = bias_results
                for k in range(self.name_index, len(bias_names)):
                    name = bias_names[k]
                    for j in range(self.keyword_index, len(secondary_terms)):
                        keyword = secondary_terms[j]
                        query = f'("{name.strip()}" AND "{keyword}")'
                        initial_url = f"{self.base_url}{self.api_path}?q={query}&api_key={self.api_key}&p=100&s=1"
                        item_results = []
                        current_url = initial_url
                        request_for_item = 1
                        total_records = 0  # Initialize total_records

                        while current_url:
                            time.sleep(1)
                            data = self.get_data_from_url(current_url, log_callback)
                            elapsed_time = time.time() - self.start_time
                            log_callback(
                                f"Springer API request {self.request_counter} made at {elapsed_time:.2f} seconds.")
                            print(f"Springer API request {self.request_counter} made at {elapsed_time:.2f} seconds.")
                            if not data:
                                break

                            if total_records == 0:
                                total_records = int(data["result"][0]["total"])
                                total_requests_for_item = -(-total_records // 100)

                            item_results.extend(self.extract_data(data))
                            current_url = data.get("nextPage", None)
                            if current_url:
                                current_url = self.base_url + current_url
                            else:
                                current_url = None  # Explicitly set to None to end the loop
                            request_for_item += 1
                            progress_callback(self.request_counter)

                        self.all_results[item]["Records"][name]["Records"][keyword] = item_results
                        self.all_results[item]["Records"][name]["Total records"] += len(item_results)
                        self.all_results[item]["Total records"] += len(item_results)
                        self.total_saved_records += len(item_results)

                        checkpoint_data = {
                            'all_results': self.all_results,
                            'total_saved_records': self.total_saved_records,
                            'item_index': i,
                            'keyword_index': j + 1,
                            'name_index': k,
                            'request_counter': self.request_counter,
                            'request_log': self.request_log
                        }
                        self.save_checkpoint(checkpoint_data)
                    self.keyword_index = 0

            self.name_index = 0

        final_output = {
            "Total": self.total_saved_records,
            "Biases": self.all_results
        }

        with open('2_springer_results.json', 'w') as file:
            json.dump(final_output, file, indent=4)

        log_callback("All results saved to '2_springer_results.json'")
        print("All results saved to '2_springer_results.json'")
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
