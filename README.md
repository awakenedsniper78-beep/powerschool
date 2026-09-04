# PowerSchool Dashboard
 
 https://awakenedsniper78-beep.github.io/powerschool/

# 🎓 Setup Your Own Grade Dashboard

This project allows you to scrape your own PowerSchool grades and host them on a private, encrypted website. **Your data is encrypted on your own computer before it ever touches the internet**, meaning only you (and anyone you give the password to) can see your grades.

## 🛠 Prerequisites
Before you start, make sure you have these installed:
*   **Python 3.10+** (Download from [python.org](https://www.python.org/))
*   **A GitHub Account** (To host your website)
*   **Git** (To upload your code)

---

## 🚀 Step-by-Step Setup

### 1. Get the Code
Open your terminal or command prompt and run:
```bash
git clone https://github.com/awakenedsniper78-beep/powerschool.git
cd powerschool
2. Install Dependencies
Install the necessary libraries to make the scraper and encryption work:

pip install -r requirements.txt
3. Configure Your Login
You need to tell the app how to log into your school's portal.

Find the file named .env.example and rename it to .env.
Open .env in a text editor and fill in your details:
PS_BASE_URL: Your school's PowerSchool URL (e.g., https://yourdistrict.powerschool.com).
PS_USERNAME: Your PowerSchool username.
PS_PASSWORD: Your PowerSchool password.
4. Scrape Your Grades
Run the scraper to fetch your current grades from the portal:

python scrape.py
This will create a file called cache.json containing your grades. This file stays on your computer and is NOT uploaded to the web.

5. Encrypt and Publish
Now, you will lock your data with a password so it can be safely put on the internet:

python publish.py
⚠️ IMPORTANT: The app will ask you to pick a Username and Password.

This is NOT your PowerSchool password.
This is a NEW password that you will use to unlock your website.
Write this password down! If you lose it, you cannot recover your data.
6. Host Your Website
Finally, upload your encrypted data to your own GitHub account:

Create a new repository on GitHub named my-grades.
Upload your files:
git remote set-url origin https://github.com/YOUR_USERNAME/my-grades.git
git add .
git commit -m "Initial setup"
git push origin main
Enable the Website:
Go to your GitHub repository $\rightarrow$ Settings $\rightarrow$ Pages.
Under "Build and deployment," set the source to Deploy from a branch.
Select the main branch and the /(root) folder.
Click Save.
🔓 How to View Your Grades
Wait about 1-2 minutes for GitHub to build your site.
Open the URL provided in the GitHub Pages settings (usually https://YOUR_USERNAME.github.io/my-grades/).
Enter the Username and Password you created in Step 5.
Your grades will decrypt instantly in your browser!
🔒 Security Reminder
Never share your .env file.
Never upload your cache.json to GitHub.
Your data is safe because it is encrypted using AES-GCM. The website only hosts the "locked" version of your data; the "key" only exists in your head.
