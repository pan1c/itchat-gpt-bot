import csv
import os
from .logging import logging
from .settings import locations_file_name

def write_csv(records):
    # The dictionary where we'll store our data, indexed by id
    data_dict = {}
    
    # Check if file exists
    if os.path.exists(locations_file_name):
        logging.debug(f"File {locations_file_name} exists")
        with open(locations_file_name, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                data_dict[int(row['id'])] = row
    
    # Update data_dict with the new records, overwriting rows with the same id
    for record in records:
        data_dict[int(record['id'])] = record
    
    # Write the updated data back to the file
    with open(locations_file_name, mode='w', newline='', encoding='utf-8') as file:
        fieldnames = ['id', 'country', 'postcode', 'label']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        
        writer.writeheader()
        for key in sorted(data_dict.keys()):
            writer.writerow(data_dict[key])
