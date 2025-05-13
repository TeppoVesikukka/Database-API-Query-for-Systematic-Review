import urllib.request
import certifi
import ssl
import json
import time
import os

class IEEEAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.end_point = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
        self.request_counter = 0
        self.start_time = time.time()
        self.request_log = ""
        self.checkpoint_file = 'checkpoint_ieee.json'
        self.all_results = {}
        self.total_saved_records = 0

        # Load checkpoint if it exists
        checkpoint_data = self.load_checkpoint()
        if checkpoint_data:
            self.all_results = checkpoint_data['all_results']
            self.total_saved_records = checkpoint_data['total_saved_records']
            self.query_index = checkpoint_data['query_index']
            self.keyword_index = checkpoint_data['keyword_index']
            self.name_index = checkpoint_data['name_index']
            self.request_counter = checkpoint_data.get('request_counter', 0)
            self.request_log = checkpoint_data.get('request_log', "")
        else:
            self.query_index = 0
            self.keyword_index = 0
            self.name_index = 0

    def load_checkpoint(self):
        """Load checkpoint data if it exists."""
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file, 'r') as f:
                return json.load(f)
        return None

    def save_checkpoint(self, data):
        """Save checkpoint data to a file."""
        data['request_counter'] = self.request_counter
        data['request_log'] = self.request_log
        with open(self.checkpoint_file, 'w') as f:
            json.dump(data, f)

    def form_query(self, bias, keyword):
        terms = [f'("{term.strip()}" AND "{keyword}")' for term in bias.split(" or ")]
        return ' OR '.join(terms)

    def call_api(self, query_text, start_record=1):
        time.sleep(1)
        url = (
            f"{self.end_point}?apikey={self.api_key}&format=json&max_records=25"
            f"&start_record={start_record}&querytext={urllib.parse.quote_plus(query_text)}"
        )
        self.request_log += f"IEEE API request #{self.request_counter + 1}: {url}\n"
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(url, context=ssl_context) as response:
            data = response.read().decode('utf-8')
        self.request_counter += 1
        return json.loads(data)

    def search(self, query_terms, keywords, log_callback, progress_callback):
        for i in range(self.query_index, len(query_terms)):
            query = query_terms[i]
            bias_names = query.split(" or ")
            if len(bias_names) == 1:
                if query not in self.all_results:
                    bias_results = {"Total records": 0, "Records": {kw: [] for kw in keywords}}
                    self.all_results[query] = bias_results
                else:
                    bias_results = self.all_results[query]
                for j in range(self.keyword_index, len(keywords)):
                    keyword = keywords[j]
                    query_text = self.form_query(query, keyword)
                    start_record = 1
                    total_records = 0
                    records_for_keyword = []

                    log_callback(f"IEEE API request {self.request_counter + 1} made.")
                    print(f"IEEE API request {self.request_counter + 1} made.")
                    while True:
                        response_data = self.call_api(query_text, start_record)

                        if total_records == 0:
                            total_records = response_data.get("total_records", 0)

                        articles = response_data.get("articles", [])
                        for article in articles:
                            title = article.get("title", "null")
                            abstract = article.get("abstract", "null")
                            authors = ', '.join([author.get("full_name", "null") for author in article.get("authors", {}).get("authors", [])])
                            doi = article.get("doi", "No DOI")
                            publication_year = article.get("publication_year", "null")
                            isbn = article.get("isbn", "null")
                            issn = article.get("issn", "null")

                            records_for_keyword.append({
                                "title": title,
                                "abstract": abstract,
                                "authors": authors,
                                "doi": doi,
                                "isbn": isbn,
                                "issn": issn,
                                "publication year": publication_year
                            })

                        if start_record + 24 >= total_records:
                            break

                        start_record += 25
                        log_callback(f"IEEE API request {self.request_counter} made at {time.time() - self.start_time:.2f} seconds.")
                        print(f"IEEE API request {self.request_counter} made at {time.time() - self.start_time:.2f} seconds.")
                        progress_callback(self.request_counter)

                    bias_results["Records"][keyword] = records_for_keyword
                    bias_results["Total records"] += len(records_for_keyword)
                    self.total_saved_records += len(records_for_keyword)

                    checkpoint_data = {
                        'all_results': self.all_results,
                        'total_saved_records': self.total_saved_records,
                        'query_index': i,
                        'keyword_index': j + 1,
                        'name_index': 0,
                        'request_counter': self.request_counter,
                        'request_log': self.request_log
                    }
                    self.save_checkpoint(checkpoint_data)
                self.keyword_index = 0

            else:
                if query not in self.all_results:
                    bias_results = {
                        "Total records": 0,
                        "Records": {name: {"Total records": 0, "Records": {kw: [] for kw in keywords}} for name in bias_names}
                    }
                    self.all_results[query] = bias_results
                else:
                    bias_results = self.all_results[query]
                for k in range(self.name_index, len(bias_names)):
                    name = bias_names[k]
                    for j in range(self.keyword_index, len(keywords)):
                        keyword = keywords[j]
                        query_text = self.form_query(name, keyword)
                        start_record = 1
                        total_records = 0
                        records_for_keyword = []

                        log_callback(f"IEEE API request {self.request_counter + 1} made.")
                        print(f"IEEE API request {self.request_counter + 1} made.")
                        while True:
                            response_data = self.call_api(query_text, start_record)

                            if total_records == 0:
                                total_records = response_data.get("total_records", 0)

                            articles = response_data.get("articles", [])
                            for article in articles:
                                title = article.get("title", "null")
                                abstract = article.get("abstract", "null")
                                authors = ', '.join([author.get("full_name", "null") for author in article.get("authors", {}).get("authors", [])])
                                doi = article.get("doi", "No DOI")
                                publication_year = article.get("publication_year", "null")
                                isbn = article.get("isbn", "null")
                                issn = article.get("issn", "null")

                                records_for_keyword.append({
                                    "title": title,
                                    "abstract": abstract,
                                    "authors": authors,
                                    "doi": doi,
                                    "isbn": isbn,
                                    "issn": issn,
                                    "publication year": publication_year
                                })

                            if start_record + 24 >= total_records:
                                break

                            start_record += 25
                            log_callback(f"IEEE API request {self.request_counter} made at {time.time() - self.start_time:.2f} seconds.")
                            print(f"IEEE API request {self.request_counter} made at {time.time() - self.start_time:.2f} seconds.")
                            progress_callback(self.request_counter)

                        bias_results["Records"][name]["Records"][keyword] = records_for_keyword
                        bias_results["Records"][name]["Total records"] += len(records_for_keyword)
                        bias_results["Total records"] += len(records_for_keyword)
                        self.total_saved_records += len(records_for_keyword)

                        checkpoint_data = {
                            'all_results': self.all_results,
                            'total_saved_records': self.total_saved_records,
                            'query_index': i,
                            'keyword_index': j + 1,
                            'name_index': k,
                            'request_counter': self.request_counter,
                            'request_log': self.request_log
                        }
                        self.save_checkpoint(checkpoint_data)
                    self.keyword_index = 0
                self.name_index = 0

            self.keyword_index = 0
            self.name_index = 0

        final_output = {
            "Total": self.total_saved_records,
            "Biases": self.all_results
        }

        with open("1_IEEE_results.json", "w") as file:
            json.dump(final_output, file, indent=4)

        log_callback("All results saved to '1_IEEE_results.json'")
        print("All results saved to '1_IEEE_results.json'")

        # Remove checkpoint file after completion
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
