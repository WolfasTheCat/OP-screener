# -*- coding: utf-8 -*-
"""
Created on Wed Apr 24 12:27:13 2024

@author: chodo

Main task of this module will be on call with parameters,
 to retrieve specific object or topic related information
 out of it's corpus
"""

def find_info_in_doc(document, find):
    stack = [document]
    path_stack = [[0]]
    
    results = {}
    low_find = [f.lower() for f in find]
    while len(stack) > 0:
        item = stack.pop()
        item_path = path_stack.pop()
        if type(item) is dict:
            search_level_of_dict(item, low_find, results, stack, path_stack, item_path)
        elif type(item) is list:
            for i in range(len(item)):
                stack.append(item[i])
                
                new_item_path = extend_item_path(item_path, i)
                path_stack.append(new_item_path)
        else:
            if type(item) is str:
                item_lc = item.lower()
                for f in low_find:
                    if f in item_lc:
                        new_item_path = extend_item_path(item_path, f)
                        add_to_dict(results, key=f, item=item, item_path=item_path)#         Found
                        #results.append({f:item})
            #else:# continue
            #    #print(type(item))
    return results

def add_to_dict(dic, key, item, item_path):
    if key not in dic:
        dic[key] = {"item":[item], "path":[item_path]}
    else:
        if item not in dic[key]["item"]:
            dic[key]["item"].append(item)
            dic[key]["path"].append(item_path)

def search_level_of_dict(item, low_find, results, stack, path_stack, item_path):
    for k in item:
        low_k = k.lower()
        if low_k in low_find:#                              if A in B:
            add_to_dict(results, key=k, item=item[k], item_path=item_path)#           Found
            #results.append({k:item[k]})
        elif item[k] in low_find:
            add_to_dict(results, key=item[k], item=item, item_path=item_path)
        else:
            skip_this_item = False
            for f in low_find:
                if f in low_k:#                             if B in A:
                    add_to_dict(results, key=k, item=item[k], item_path=item_path)#   Found
                    skip_this_item = True
                    #results.append({k:item[k]})
                elif isinstance(item[k], (str, dict, list)) and f in item[k]:
                    add_to_dict(results, key=f, item=item, item_path=item_path)
                    skip_this_item = True
            if not skip_this_item:
                stack.append(item[k])
                new_item_path = extend_item_path(item_path, k)
                path_stack.append(new_item_path)


def extend_item_path(parent_path, node_sub_path):
    if parent_path is not None and parent_path[0] is not None:
        new_item_path = parent_path.copy()
        new_item_path.append(node_sub_path)
    else:
        new_item_path = [node_sub_path]
    return new_item_path

