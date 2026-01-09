Automated Trading Card Analysis Platform
 specialized automation tool designed to identify undervalued trading card lots on ShopGoodwill.com using Google’s Gemini 2.0 Flash models. It handles the entire pipeline: logging in, searching for listings, downloading high-resolution images, and performing deep-dive financial analysis to calculate potential ROI.

Key Features
Multimodal AI Analysis: Leverages Gemini's vision capabilities to see card conditions, identify specific sets/parallels, and detect potential fakes.

Dual API Key Rotation: Features an APIRotator class that cycles through multiple API keys and models to maximize daily processing limits (up to 80 items per day).

Automated Financial Modeling: The AI prompt is specifically engineered to calculate net profit after a 15% selling fee and acquisition costs.

Headless Integration: Uses encrypted authentication to interact with the ShopGoodwill buyer API.

Automated Email Reports: Sends a daily HTML summary of Strong Buy, Buy, and Pass recommendations directly to your inbox.

Installation
Clone the repository:

Bash


Install dependencies:

Bash

pip install requests pycryptodome google-generativeai Pillow python-dotenv
Configure Environment Variables: Create a .env file in the root directory and populate it with your credentials:

Plaintext

SGW_SECRET_KEY=6696D2E6F042FEC4D6E3F32AD541143B
SGW_IV=0000000000000000
SGW_USER=your_shopgoodwill_username
SGW_PASS=your_shopgoodwill_password
GEMINI_API_KEYS=key_one,key_two
EMAIL_SENDER=your_gmail@gmail.com
EMAIL_APP_PASSWORD=your_google_app_password
EMAIL_RECIPIENT=destination_email@gmail.com
How It Works
Authentication: The script encrypts your credentials using AES-CBC encryption to securely authenticate with the ShopGoodwill API.

Scraping and Imaging: It fetches listing metadata and downloads all available images for each item in your search criteria.

Vision Processing: Images are resized and optimized for token efficiency before being sent to the Gemini 2.0 Flash models.

Grading and Valuation: The AI acts as a professional trader, identifying cards worth $20+, estimating condition (PSA/Raw), and looking for red flags like water damage or overgrading.

Reporting: Results are saved locally to shopgoodwill_results.json and a ranked summary is emailed to you.

Security Note
Never commit your .env file to GitHub. This project includes a .gitignore template to prevent your ShopGoodwill credentials, API keys, and local image cache from being uploaded to public repositories.

Disclaimer
This tool is for educational and research purposes. Users are responsible for ensuring their use of automation scripts complies with the Terms of Service of the platforms involved.
