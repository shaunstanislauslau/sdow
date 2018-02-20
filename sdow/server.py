"""
Server web framework.
"""

import time
from sets import Set
from flask_cors import CORS
from sdow.database import Database
from sdow.helpers import InvalidRequest
from flask import Flask, request, jsonify

import requests

WIKIPEDIA_API_URL = 'https://en.wikipedia.org/w/api.php'


sqlite_filename = '../sdow.sqlite'

# TODO: figure out how to pass CLI arguments to Flask
# See http://flask.pocoo.org/snippets/133/
# if len(sys.argv) != 2:
#   print '[ERROR] Invalid program usage.'
#   print '[INFO] Usage: server.py <sqlite_file>'
#   sys.exit(1)

# sqlite_file = sys.argv[1]

database = Database(sqlite_filename)

app = Flask(__name__)

# TODO: do I want this setup in production
CORS(app)


@app.errorhandler(InvalidRequest)
def handle_invalid_usage(error):
  response = jsonify(error.to_dict())
  response.status_code = error.status_code
  return response


@app.route('/paths', methods=['POST'])
def shortest_paths_route():
  """Endpoint which returns a list of shortest paths between two Wikipedia pages.

    Args:
      source: The title of the page at which to start the search.
      target: The title of the page at which to end the search.

    Returns:
      dict: A JSON-ified dictionary containing the shortest paths (represented by a list of lists of
            page IDs)and the corresponding pages data (represented by a dictionary of page IDs).

    Raises:
      InvalidRequest: If either of the provided titles correspond to pages which do not exist.
  """
  start_time = time.time()

  from_page_title = request.json['source']
  to_page_title = request.json['target']

  # Look up the IDs for each page
  try:
    from_page_id = database.fetch_page_id(from_page_title)
  except ValueError:
    raise InvalidRequest(
        'Start page "{0}" does not exist. Please try another search.'.format(from_page_title))

  try:
    to_page_id = database.fetch_page_id(to_page_title)
  except ValueError:
    raise InvalidRequest(
        'End page "{0}" does not exist. Please try another search.'.format(to_page_title))

  # Compute the shortest paths
  paths = database.compute_shortest_paths(from_page_id, to_page_id)

  if len(paths) == 0:
    # No paths found
    response = {
        'paths': [],
        'pages': [],
    }
  else:
    # Paths found

    # Get a list of all IDs
    page_ids_set = Set()
    for path in paths:
      for page_id in path:
        page_ids_set.add(str(page_id))

    page_ids_list = list(page_ids_set)
    pages_info = {}

    current_page_ids_index = 0
    while current_page_ids_index < len(page_ids_list):
      # Query at most 50 pages per request (given WikiMedia API limits)
      end_page_ids_index = min(
          current_page_ids_index + 50, len(page_ids_list))

      query_params = {
          'action': 'query',
          'format': 'json',
          'pageids': '|'.join(page_ids_list[current_page_ids_index:end_page_ids_index]),
          'prop': 'info|pageimages|pageterms',
          'inprop': 'url|displaytitle',
          'piprop': 'thumbnail',
          'pithumbsize': 160,
          'pilimit': 50,
          'wbptterms': 'description',
      }

      current_page_ids_index = end_page_ids_index

      req = requests.get(WIKIPEDIA_API_URL, params=query_params)

      pages_result = req.json().get('query', {}).get('pages')

      for page_id, page in pages_result.iteritems():
        dev_page_id = int(page_id)

        pages_info[dev_page_id] = {
            'title': page['title'],
            'url': page['fullurl']
        }

        thumbnail_url = page.get('thumbnail', {}).get('source')
        if thumbnail_url:
          pages_info[dev_page_id]['thumbnailUrl'] = thumbnail_url

        description = page.get('terms', {}).get('description', [])
        if description:
          pages_info[dev_page_id]['description'] = description[0][0].upper() + description[0][1:]

    response = {
        'paths': paths,
        'pages': pages_info
    }

  database.insert_result({
      'source_id': from_page_id,
      'target_id': to_page_id,
      'duration': time.time() - start_time,
      'paths': paths,
  })

  return jsonify(response)


if __name__ == '__main__':
  app.run()
