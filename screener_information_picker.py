"""
Created on Wed Apr 24 12:27:13 2024

@author: chodo

Main task of this module will be on call with parameters,
to retrieve specific object or topic-related information
out of its corpus
"""


def find_info_in_doc(document, find):
    """
    This function takes a document (which can be a nested structure such as a dictionary or list)
    and a list of terms ('find'). It traverses through the document, searching for occurrences
    of the specified terms in the keys or values, and returns the results in a dictionary.

    Parameters:
    - document: A nested data structure (could be a dictionary or list) to search within.
    - find: A list of strings representing the search terms.

    Returns:
    - results: A dictionary where the key is the found term, and the value is another dictionary containing:
        - 'item': the content where the search term was found.
        - 'path': the path within the document where the item was found.
    """

    stack = [document]  # Stack to hold the current items to process in the document.
    path_stack = [[0]]  # Stack to hold the corresponding paths for the items in the document.

    results = {}  # Dictionary to store the found results.

    # Convert all search terms to lowercase for case-insensitive search.
    low_find = [f.lower() for f in find]

    # Depth-first search loop.
    while len(stack) > 0:
        item = stack.pop()  # Retrieve the last item from the stack.
        item_path = path_stack.pop()  # Retrieve the corresponding path.

        # If the current item is a dictionary, search within its keys.
        if type(item) is dict:
            search_level_of_dict(item, low_find, results, stack, path_stack, item_path)

        # If the current item is a list, process each element in the list.
        elif type(item) is list:
            for i in range(len(item)):
                stack.append(item[i])  # Push each element onto the stack.
                new_item_path = extend_item_path(item_path, i)  # Extend the path for each element.
                path_stack.append(new_item_path)

        # If the current item is a string, search for the term within the string.
        else:
            if type(item) is str:
                item_lc = item.lower()  # Convert string to lowercase for case-insensitive comparison.
                for f in low_find:
                    if f in item_lc:  # Check if the search term is in the string.
                        new_item_path = extend_item_path(item_path, f)  # Create a new path for the found item.
                        add_to_dict(results, key=f, item=item, item_path=item_path)  # Add the result to the dictionary.

    return results  # Return the results dictionary.


def add_to_dict(dic, key, item, item_path):
    """
    Helper function to add an item to the results dictionary. It ensures that the search term
    (key) and its associated content (item) are stored in the dictionary along with the path.

    Parameters:
    - dic: The dictionary where the results are stored.
    - key: The term that was found.
    - item: The content where the search term was found.
    - item_path: The path within the document where the item was found.
    """

    if key not in dic:
        # If the key doesn't exist, initialize it with the 'item' and 'path' details.
        dic[key] = {"item": [item], "path": [item_path]}
    else:
        # If the key already exists, ensure the item isn't duplicated.
        if item not in dic[key]["item"]:
            dic[key]["item"].append(item)
            dic[key]["path"].append(item_path)


def search_level_of_dict(item, low_find, results, stack, path_stack, item_path):
    """
    Helper function to search for terms within a dictionary's keys or values.

    Parameters:
    - item: The current dictionary being searched.
    - low_find: The list of search terms (in lowercase).
    - results: The dictionary where results are stored.
    - stack: The stack of items to process.
    - path_stack: The stack of paths corresponding to items.
    - item_path: The current path in the document.
    """

    for k in item:
        low_k = k.lower()  # Convert the key to lowercase for case-insensitive comparison.

        # Check if the search term is in the key.
        if low_k in low_find:
            add_to_dict(results, key=k, item=item[k], item_path=item_path)

        # Check if the search term is directly in the value.
        elif item[k] in low_find:
            add_to_dict(results, key=item[k], item=item, item_path=item_path)

        else:
            skip_this_item = False
            for f in low_find:
                if f in low_k:  # If the term is part of the key, add it to the results.
                    add_to_dict(results, key=k, item=item[k], item_path=item_path)
                    skip_this_item = True
                elif isinstance(item[k], (str, dict, list)) and f in item[k]:  # Check for term in value.
                    add_to_dict(results, key=f, item=item, item_path=item_path)
                    skip_this_item = True

            # If the current item is not directly related to the search term, add it to the stack for further processing.
            if not skip_this_item:
                stack.append(item[k])
                new_item_path = extend_item_path(item_path, k)
                path_stack.append(new_item_path)


def extend_item_path(parent_path, node_sub_path):
    """
    Helper function to extend the current path with a new node.

    Parameters:
    - parent_path: The current path in the document.
    - node_sub_path: The new node to add to the path.

    Returns:
    - new_item_path: The extended path.
    """

    if parent_path is not None and parent_path[0] is not None:
        new_item_path = parent_path.copy()  # Copy the existing path.
        new_item_path.append(node_sub_path)  # Append the new node.
    else:
        new_item_path = [node_sub_path]  # Initialize a new path if none exists.

    return new_item_path

