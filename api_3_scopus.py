import requests
import json
import time
import os

class ScopusAPI:
    def __init__(self, api_key, insttoken):
        self.api_key = api_key
        self.insttoken = insttoken
        self.base_url = "https://api.elsevier.com/content/search/scopus"
        self.max_requests_per_day = 500
        self.request_counter = 0
        self.start_time = time.time()
        self.checkpoint_file = 'checkpoint_scopus.json'
        self.all_results = {}
        self.total_saved_records = 0
        self.request_log = ""  # Initialize request_log

        # Load checkpoint if it exists
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
            log_callback(f"Scopus API reached {self.max_requests_per_day} requests. Pausing for 24 hours.")
            print(f"Scopus API Reached {self.max_requests_per_day} requests. Pausing for 24 hours.")
            time.sleep(24 * 60 * 60)  # Sleep for 24 hours
            self.request_counter = 0  # Reset the counter after sleep
        self.request_log += f"Scopus API request #{self.request_counter + 1}: {url}\n"  # Log the request URL
        response = requests.get(url)
       # log_callback(f"Status Code: {response.status_code}")
        if response.status_code != 200:
            return None
        data = response.json()
        self.request_counter += 1
        return data

    def extract_titles_and_abstracts(self, data):
        results = []
        for entry in data.get('search-results', {}).get('entry', []):
            # Extract the required information for each entry
            article_data = {
                "title": entry.get("dc:title"),
                "abstract": entry.get("dc:description"),
                "authors": ', '.join([author.get("authname", "null") for author in entry.get("author", [])]),
                "doi": entry.get("prism:doi"),
                "isbn": entry.get("prism:isbn", "null"),
                "issn": entry.get("prism:issn", "null"),
                "publication year": entry.get("prism:coverDate", "").split("-")[0]  # Extract year from coverDate
            }
            if any(article_data.values()):  # Only add if there's at least one non-null value
                results.append(article_data)
        return results

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
                    initial_url = f"{self.base_url}?query={query}&httpAccept=application%2Fjson&count=25&view=COMPLETE&apikey={self.api_key}&insttoken={self.insttoken}"
                    item_results = []
                    current_url = initial_url
                    request_for_item = 1
                    total_records = 0  # Initialize total_records

                    while current_url:
                        time.sleep(1)
                        data = self.get_data_from_url(current_url, log_callback)
                        elapsed_time = time.time() - self.start_time
                        log_callback(f"Scopus API request {self.request_counter} made at {elapsed_time:.2f} seconds.")
                        print(f"Scopus API request {self.request_counter} made at {elapsed_time:.2f} seconds.")
                        if not data:
                            break

                        if total_records == 0 and 'search-results' in data and 'opensearch:totalResults' in data[
                            'search-results']:
                            total_records = int(data['search-results']['opensearch:totalResults'])
                            total_requests_for_item = -(-total_records // 25)

                        item_results.extend(self.extract_titles_and_abstracts(data))
                        next_link = next(
                            (link['@href'] for link in data['search-results']['link'] if link['@ref'] == 'next'), None)
                        current_url = next_link if next_link else None
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
                        initial_url = f"{self.base_url}?query={query}&httpAccept=application%2Fjson&count=25&view=COMPLETE&apikey={self.api_key}&insttoken={self.insttoken}"
                        item_results = []
                        current_url = initial_url
                        request_for_item = 1
                        total_records = 0  # Initialize total_records

                        while current_url:
                            time.sleep(1)
                            data = self.get_data_from_url(current_url, log_callback)
                            elapsed_time = time.time() - self.start_time
                            log_callback(
                                f"Scopus API request {self.request_counter} made at {elapsed_time:.2f} seconds.")
                            print(f"Scopus API request {self.request_counter} made at {elapsed_time:.2f} seconds.")
                            if not data:
                                break

                            if total_records == 0 and 'search-results' in data and 'opensearch:totalResults' in data[
                                'search-results']:
                                total_records = int(data['search-results']['opensearch:totalResults'])
                                total_requests_for_item = -(-total_records // 25)

                            item_results.extend(self.extract_titles_and_abstracts(data))
                            next_link = next(
                                (link['@href'] for link in data['search-results']['link'] if link['@ref'] == 'next'),
                                None)
                            current_url = next_link if next_link else None
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

        with open('3_scopus_results.json', 'w') as file:
            json.dump(final_output, file, indent=4)

        log_callback("All results saved to '3_scopus_results.json'")
        print("All results saved to '3_scopus_results.json'")

        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)

