# -*- coding: utf-8 -*-
"""
Created on Thu Apr  4 18:51:27 2024
                                                                                                                                                                                                                                                                
@author: chodo
Spin-off of ir_preprocessor.py by the same author
"""

import json
from enum import Enum
import re
import os
import time

_url_to_file_suffix_len = 8# for long urls, unique part probably comes in the end
max_file_name_len = 64

class Convertions(Enum):
    JSON_TO_DICT = 0
    HTML = 5
    NONE = None


def json_to_dict(fp):
    raw = load_file(fp)
    data_as_dict = json.loads(raw)
    return data_as_dict

def load_html(fp):
    raw = load_file(fp)
    return raw


def ns_to_s(ns):
    s = ns/1_000_000_000
    return s

def url_to_file_name(url):
    file_name = url.split("//")[-1].replace(".", "_")#.replace("/", "-").replace("?","")
    pattern = r'[<>:"/\\|?*^/|%|&]'
    file_name = re.sub(pattern, '', file_name)
    return file_name

def is_web_url(text):
    # Regular expression pattern for matching URLs
    url_pattern = re.compile(r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘’]))')
    
    # Check if the text matches the URL pattern
    return bool(re.match(url_pattern, text))

def load_file(file_path):
    lines = None
    with open(file_path, 'r', encoding="utf-8") as file:
        lines = file.readlines()
    
        #(normalized_text)
    txt =""
    for l in lines:
        txt += l+" "
    return txt[:-1]
 
def folder(path):
    """
    create if does not exist, ensures the path
    """
    folder_path = path
    if not folder_path.endswith("/"):
        folder_path += "/"
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path

def file_name_to_acceptable_length(file_name):
    if len(file_name) > max_file_name_len:# ~256, can be extended up to 32_000
        file_name = file_name[0:max_file_name_len]+file_name[-_url_to_file_suffix_len:]# for uniqueness   
    return file_name

def list_dir(directory):
    for dirpath,_,filenames in os.walk(directory):
        for f in filenames:
            yield os.path.abspath(os.path.join(dirpath, f))

class My_dataset:
    #stop_words = ...
    dataset = None
    
    _max_dataset_size = None
    
    loading_time = 0
    _t0 = 0
    def __init__(self, max_dataset_size=None):
        #self.stop_words = stop_words
        self._max_dataset_size = max_dataset_size
        if self.dataset is None:
            self.dataset = {}
    
    def append_data(self, url, text):
        self.dataset[url] = text
    
    def load_dataset(self, path, search_stack = None, load_as=Convertions.NONE):
        self._start_timer()
        if search_stack is None:
            search_stack = [path]
        
        if load_as is Convertions.JSON_TO_DICT:
            loading_fun = json_to_dict
        elif load_as is Convertions.HTML:
            loading_fun = load_html
        else:
            loading_fun = load_file
        
        while len(search_stack) >= 1:
            directory = search_stack.pop()
            for item_path in list_dir(directory):
                if os.path.isdir(item_path):
                    search_stack.append(item_path)
                else:
                    self.dataset[item_path] = loading_fun(item_path)
                if self._max_dataset_size is not None:
                    self._max_dataset_size -= 1
                    if self._max_dataset_size == 0:
                        self._stop_timer()
                        return
        self._stop_timer()
        
    def _start_timer(self):
        self._t0 = time.time_ns()
    
    def _stop_timer(self):
        self.loading_time = ns_to_s(time.time_ns() - self._t0)
    
    
    def convert_dataset(self, to):
        if to is not Convertions.JSON_TO_DICT:
            return None
        for k in self.dataset:
            self.dataset[k] = json_to_dict(self.dataset[k])
    