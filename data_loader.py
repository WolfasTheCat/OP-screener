# -*- coding: utf-8 -*-
"""
Created on Thu Apr  4 18:51:27 2024

@author: chodo
Spin-off of ir_preprocessor.py by the same author
"""
# This module provides utilities for loading datasets from various file formats (text, HTML, JSON),
# performing basic preprocessing, and working with URLs and file structures.

import json  # Used for handling JSON data
from enum import Enum  # Used for creating enumerations to handle various types of conversions
import re  # Regular expressions, used here for pattern matching (e.g., URL validation)
import os  # Used for file and directory operations
import time  # Used to measure loading time for datasets

# Global variables that limit file naming conventions
_url_to_file_suffix_len = 8  # To get a unique part of long URLs from the end
max_file_name_len = 64  # Maximum length of the filename


# Enum to represent different conversion types
class Convertions(Enum):
    JSON_TO_DICT = 0  # Convert JSON files to Python dictionaries
    HTML = 5  # Load files as raw HTML
    NONE = None  # No specific conversion required


# Converts a JSON file into a Python dictionary
def json_to_dict(fp):
    raw = load_file(fp)  # Load the raw content from the file
    data_as_dict = json.loads(raw)  # Convert raw JSON string to a dictionary
    return data_as_dict


# Loads an HTML file as a raw string
def load_html(fp):
    raw = load_file(fp)  # Loads the raw content from the file
    return raw


# Converts nanoseconds to seconds
def ns_to_s(ns):
    s = ns / 1_000_000_000  # 1 second = 1,000,000,000 nanoseconds
    return s


# Converts a URL into a valid filename by replacing certain characters
def url_to_file_name(url):
    file_name = url.split("//")[-1].replace(".", "_")  # Replace dots with underscores
    pattern = r'[<>:"/\\|?*^/|%|&]'  # Define characters that are invalid in filenames
    file_name = re.sub(pattern, '', file_name)  # Replace invalid characters with empty strings
    return file_name


# Determines if a string is a valid URL by matching it against a URL pattern
def is_web_url(text):
    url_pattern = re.compile(
        r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘’]))')
    return bool(re.match(url_pattern, text))  # Returns True if the text is a valid URL


# Reads the entire content of a file and returns it as a single string
def load_file(file_path):
    lines = None
    # Open the file with UTF-8 encoding
    with open(file_path, 'r', encoding="utf-8") as file:
        lines = file.readlines()  # Read all lines of the file
    txt = ""  # Initialize an empty string
    for l in lines:
        txt += l + " "  # Append each line to the string, separating by spaces
    return txt[:-1]  # Return the concatenated text


# Ensures the directory exists and creates it if it does not
def folder(path):
    folder_path = path
    if not folder_path.endswith("/"):  # Ensure the path ends with a slash
        folder_path += "/"
    if not os.path.exists(folder_path):  # If the directory doesn't exist, create it
        os.makedirs(folder_path)
    return folder_path  # Return the valid folder path


# Shortens filenames that are too long by truncating them
def file_name_to_acceptable_length(file_name):
    if len(file_name) > max_file_name_len:  # Check if the filename exceeds the maximum length
        file_name = file_name[0:max_file_name_len] + file_name[-_url_to_file_suffix_len:]  # Truncate and append suffix
    return file_name


# Recursively lists all files in a directory and its subdirectories
def list_dir(directory):
    for dirpath, _, filenames in os.walk(directory):  # os.walk generates file names in a directory tree
        for f in filenames:  # Iterate over all filenames in the directory
            yield os.path.abspath(os.path.join(dirpath, f))  # Yield the absolute path of each file


# Class to handle datasets with functionalities for loading and converting them
class My_dataset:
    dataset = None  # Dataset is initially empty
    _max_dataset_size = None  # Limit on the number of files to load
    loading_time = 0  # Tracks the time taken to load the dataset
    _t0 = 0  # Start time of the loading process

    # Constructor for the dataset, initializes the dataset and size limit
    def __init__(self, max_dataset_size=None):
        self._max_dataset_size = max_dataset_size  # Set the maximum dataset size if provided
        if self.dataset is None:  # If the dataset hasn't been initialized, initialize it as an empty dictionary
            self.dataset = {}

    # Appends data (a URL and its corresponding text) to the dataset
    def append_data(self, url, text):
        self.dataset[url] = text

    # Loads files from the specified directory into the dataset, optionally applying a conversion
    def load_dataset(self, path, search_stack=None, load_as=Convertions.NONE):
        self._start_timer()  # Start timing the loading process
        if search_stack is None:
            search_stack = [path]  # If no search stack is provided, initialize it with the root path

        # Determine which loading function to use based on the conversion type
        if load_as is Convertions.JSON_TO_DICT:
            loading_fun = json_to_dict  # Convert JSON to dictionary
        elif load_as is Convertions.HTML:
            loading_fun = load_html  # Load HTML content as a string
        else:
            loading_fun = load_file  # Default: Load plain text file

        # Recursively search through directories and load files
        while len(search_stack) >= 1:
            directory = search_stack.pop()
            for item_path in list_dir(directory):  # List all files in the current directory
                if os.path.isdir(item_path):
                    search_stack.append(item_path)  # If it's a directory, add it to the stack
                else:
                    self.dataset[item_path] = loading_fun(item_path)  # Load the file content and add it to the dataset
                # Stop loading if the maximum dataset size is reached
                if self._max_dataset_size is not None:
                    self._max_dataset_size -= 1
                    if self._max_dataset_size == 0:
                        self._stop_timer()  # Stop timing the process
                        return
        self._stop_timer()  # Stop timing when all files are loaded

    # Start the timer to track how long the loading process takes
    def _start_timer(self):
        self._t0 = time.time_ns()  # Get the current time in nanoseconds

    # Stop the timer and calculate the total loading time
    def _stop_timer(self):
        self.loading_time = ns_to_s(time.time_ns() - self._t0)  # Calculate the loading time in seconds

    # Converts the dataset to the specified format (currently only supports JSON to dict conversion)
    def convert_dataset(self, to):
        if to is not Convertions.JSON_TO_DICT:  # Currently only JSON to dictionary conversion is supported
            return None
        for k in self.dataset:  # Iterate over all items in the dataset
            self.dataset[k] = json_to_dict(self.dataset[k])  # Convert each item to a dictionary
