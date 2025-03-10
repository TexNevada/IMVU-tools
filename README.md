# IMVU-tools

## Requirement
Run with Python 3.6 or higher or run the exe file. 

## What does this script do?
IMVU by default only handles 3 concurrent requests. This slows down the client significantly. 
By changing the MAX_CONCURRENT_REQUESTS value we can increase the speed in which the client fetches assets.

This script just replaces the default DownloadManager.pyo file in the imvu library with one that has the MAX_CONCURRENT_REQUESTS set to a higher value. 
Feel free to inspect the py files or even decompile the pyo's.