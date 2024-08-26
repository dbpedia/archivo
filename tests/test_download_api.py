import unittest
import subprocess
import time
import requests
import os
import hashlib


class TestServerResponses(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.chdir("archivo")
        # Start the server
        cls.server_process = subprocess.Popen(["poetry", "run", "python", "archivo.py"])
        # Give the server some time to start up
        time.sleep(5)


    @classmethod
    def tearDownClass(cls):
        # Shut down the server
        cls.server_process.terminate()
        cls.server_process.wait()


    def test_response_second_url(self):
        url = "http://localhost:5000/download?o=http%3A//comicmeta.org/cbo/&f=owl&v=2023.03.18-185709&vM=closest"
        response = requests.get(url)
        
        # Calculate the MD5 checksum of the content
        md5_hash = hashlib.md5(response.content).hexdigest()
        expected_md5 = "4176659915aaacc0b7960dd7428d5439"
        self.assertEqual(md5_hash, expected_md5)


    def test_response_first_url(self):
        url = "http://localhost:5000/download?o=http%3A//comicmeta.org/cbo/&f=owl&v=2024.05.29-031359&vM=closest"
        response = requests.get(url)
        
        # Calculate the MD5 checksum of the content
        md5_hash = hashlib.md5(response.content).hexdigest()
        expected_md5 = "4196656da08e5b248dc1a9eaca3c888c"
        self.assertEqual(md5_hash, expected_md5)


if __name__ == '__main__':
    unittest.main()