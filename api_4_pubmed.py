import requests
import xml.etree.ElementTree as ET
import json
import time
import os

class PubMedAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.esearch_path = "/esearch.fcgi"
        self.efetch_path = "/efetch.fcgi"
        self.max_requests_per_day = 500
        self.request_counter = 0
        self.start_time = time.time()
        self.request_log = ""
        self.checkpoint_file = 'checkpoint_pubmed.json'
        self.all_results = {}
        self.total_saved_records = 0

        # Load checkpoint if it exists
        checkpoint_data = self.load_checkpoint()
        if checkpoint_data:
            self.all_results = checkpoint_data['all_results']
            self.total_saved_records = checkpoint_data['total_saved_records']
            self.item_index = checkpoint_data['item_index']
            self.keyword_index = checkpoint_data['keyword_index']
            self.name_index = checkpoint_data['name_index']
            self.request_counter = checkpoint_data.get('request_counter', 0)
            self.request_log = checkpoint_data.get('request_log', "")
        else:
            self.item_index = 0
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

    def get_data_from_url(self, url, log_callback):
        if self.request_counter >= self.max_requests_per_day:
            log_callback(f"PubMed API reached {self.max_requests_per_day} requests. Pausing for 24 hours.")
            print(f"PubMed API reached {self.max_requests_per_day} requests. Pausing for 24 hours.")
            time.sleep(24 * 60 * 60)  # Sleep for 24 hours
            self.request_counter = 0  # Reset the counter after sleep
        self.request_log += f"PubMed API request #{self.request_counter + 1}: {url}\n"
        response = requests.get(url)
        self.request_counter += 1
        return response.content  # Since we're dealing with XML, return raw content

    def extract_pubmed_data(self, xml_content):
        """Extract relevant data from PubMed XML content."""
        root = ET.fromstring(xml_content)
        articles = []

        for pubmed_article in root.findall('PubmedArticle'):
            article_data = {}

            medline_citation = pubmed_article.find('MedlineCitation')
            if medline_citation is None:
                continue

            article_title = medline_citation.find('Article/ArticleTitle')
            article_data['title'] = article_title.text if article_title is not None else "null"

            article = medline_citation.find('Article')

            abstract = article.find('Abstract/AbstractText') if article is not None else None
            if abstract is not None:
                article_data['abstract'] = abstract.text

            article_ids = pubmed_article.find('PubmedData/ArticleIdList')
            if article_ids is not None:
                for article_id in article_ids:
                    if article_id.attrib.get('IdType') == 'doi':
                        article_data['doi'] = article_id.text
                    elif article_id.attrib.get('IdType') == 'isbn':
                        article_data['isbn'] = article_id.text

            journal = article.find('Journal') if article is not None else None
            issn = journal.find('ISSN') if journal is not None else None
            if issn is not None:
                article_data['issn'] = issn.text

            pub_date = article.find('Journal/JournalIssue/PubDate/Year') if article is not None else None
            if pub_date is not None:
                article_data['publication year'] = pub_date.text

            authors = article.find('AuthorList') if article is not None else None
            if authors is not None:
                author_names = [
                    (author.find('LastName').text + " " + author.find('ForeName').text)
                    if author.find('LastName') is not None and author.find('ForeName') is not None
                    else "null"
                    for author in authors.findall('Author')
                ]
                article_data['authors'] = ', '.join(author_names)

            if any(article_data.values()):
                articles.append(article_data)

        return articles


    def get_pmids_for_search_term(self, search_term, log_callback):
        pmids = []
        retstart = 0
        retmax = 100

        term1, term2 = search_term.split(' AND ')
        query = f'%22{term1.replace(" ", "+")}%22+AND+%22{term2.replace(" ", "+")}%22'

        while True:
            esearch_url = f"{self.base_url}{self.esearch_path}?db=pubmed&term={query}&retstart={retstart}&retmax={retmax}&api_key={self.api_key}"
            esearch_response = self.get_data_from_url(esearch_url, log_callback)
            log_callback(f"PubMed API request {self.request_counter} made.")
            print(f"PubMed API request {self.request_counter} made.")
            root = ET.fromstring(esearch_response)

            current_pmids = [pmid.text for pmid in root.findall('IdList/Id')]
            if not current_pmids:
                break

            pmids.extend(current_pmids)
            retstart += retmax

        return pmids

    def search(self, initial_terms, secondary_terms, log_callback, progress_callback):
        for i in range(self.item_index, len(initial_terms)):
            item = initial_terms[i]
            bias_names = item.split(" or ")
            if len(bias_names) == 1:
                if item not in self.all_results:
                    bias_results = {"Total records": 0, "Records": {kw: [] for kw in secondary_terms}}
                    self.all_results[item] = bias_results
                else:
                    bias_results = self.all_results[item]
                for j in range(self.keyword_index, len(secondary_terms)):
                    keyword = secondary_terms[j]
                    search_term = f'{bias_names[0].strip()} AND {keyword}'
                    pmids = self.get_pmids_for_search_term(search_term, log_callback)
                    item_results = []

                    if not pmids:
                        continue

                    for k in range(0, len(pmids), 100):
                        pmid_chunk = ",".join(pmids[k:k + 100])
                        efetch_url = f"{self.base_url}{self.efetch_path}?db=pubmed&id={pmid_chunk}&retmode=xml&api_key={self.api_key}"
                        efetch_response = self.get_data_from_url(efetch_url, log_callback)
                        item_results.extend(self.extract_pubmed_data(efetch_response))
                        log_callback(f"PubMed API request {self.request_counter} made.")
                        print(f"PubMed API request {self.request_counter} made.")
                        progress_callback(self.request_counter)

                    bias_results["Records"][keyword] = item_results
                    bias_results["Total records"] += len(item_results)
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
                self.keyword_index = 0

            else:
                if item not in self.all_results:
                    bias_results = {
                        "Total records": 0,
                        "Records": {name: {"Total records": 0, "Records": {kw: [] for kw in secondary_terms}} for name in bias_names}
                    }
                    self.all_results[item] = bias_results
                else:
                    bias_results = self.all_results[item]
                for k in range(self.name_index, len(bias_names)):
                    name = bias_names[k]
                    for j in range(self.keyword_index, len(secondary_terms)):
                        keyword = secondary_terms[j]
                        search_term = f'{name.strip()} AND {keyword}'
                        pmids = self.get_pmids_for_search_term(search_term, log_callback)
                        item_results = []

                        if not pmids:
                            continue

                        for l in range(0, len(pmids), 100):
                            pmid_chunk = ",".join(pmids[l:l + 100])
                            efetch_url = f"{self.base_url}{self.efetch_path}?db=pubmed&id={pmid_chunk}&retmode=xml&api_key={self.api_key}"
                            efetch_response = self.get_data_from_url(efetch_url, log_callback)
                            item_results.extend(self.extract_pubmed_data(efetch_response))
                            log_callback(f"PubMed API request {self.request_counter} made.")
                            print(f"PubMed API request {self.request_counter} made.")
                            progress_callback(self.request_counter)

                        bias_results["Records"][name]["Records"][keyword] = item_results
                        bias_results["Records"][name]["Total records"] += len(item_results)
                        bias_results["Total records"] += len(item_results)
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

            self.keyword_index = 0
            self.name_index = 0

        final_output = {
            "Total": self.total_saved_records,
            "Biases": self.all_results
        }

        with open('4_pubmed_results_all.json', 'w') as file:
            json.dump(final_output, file, indent=4)

        log_callback("All results saved to '4_pubmed_results_all.json'")
        print("All results saved to '4_pubmed_results_all.json'")

        # Remove checkpoint file after completion
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)












