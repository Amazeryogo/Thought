from routes import *
from waitress import serve
print("Starting Thought at \n"+ "http://0.0.0.0:8080 on "+str(bruh.now().time()))
serve(appx, host='0.0.0.0', port=os.environ['PORT'])
