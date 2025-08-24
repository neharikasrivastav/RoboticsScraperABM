A research + engineering project that combines **web scraping, AI/ML models, and real-time visualization** to extract and analyze robotics-related data.  
Built with **Python, Streamlit, Supabase, and Playwright**.

---

## 🚀 Project Overview
- Designed a pipeline to scrape robotics company data from multiple online sources.  
- Stored structured + unstructured data in **Supabase** for scalable access.  
- Applied **AI/ML + NLP models** to extract insights (funding, sector, geography, etc.).  
- Built a **Streamlit dashboard** to visualize robotics industry trends in real-time.  

This project demonstrates skills in **data engineering, automation, applied ML, and full-stack deployment**.

---

## 🛠️ Tech Stack
- **Python** (automation, data cleaning, ML/NLP models)  
- **Supabase** (Postgres backend for storing scraped data)  
- **Playwright** (headless browser scraping)  
- **Streamlit** (interactive dashboard)  
- **Docker** (containerized deployment)  

---

## 📂 Project Structure
- `requirements.txt` → Python dependencies  
- `streamlit_app.py` → Dashboard entry point  
- `scraper/` → Playwright scraping scripts  
- `models/` → AI/NLP models for classification  
- `.env` → Environment variables (API keys, Supabase credentials)  

---

## 🔧 Setup Instructions
1. Install dependencies:  
   ```bash
   pip install -r requirements.txt

#  Install dependencies
pip install -r requirements.txt


# . Regarding Supabase   
        1. **[Create a free Supabase account](https://supabase.com/)**.
        2. **Create a new project** inside Supabase.
        3. **Create a table** in your project by running the following SQL command in the **SQL Editor**:
        
        ```sql
        CREATE TABLE IF NOT EXISTS scraped_data (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        unique_name TEXT NOT NULL,
        url TEXT,
        raw_data JSONB,        
        formatted_data JSONB, 
        pagination_data JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW()
        );
        ```

        4. **Go to Project Settings → API** and copy:
            - **Supabase URL**
            - **Anon Key**
        
        5. **Update your `.env` file** with these values:
        
        ```
        SUPABASE_URL=your_supabase_url_here
        SUPABASE_ANON_KEY=your_supabase_anon_key_here
        ```

        6. **Restart the project** and you’re good to go! 


##  run "playwright install"

## add your api keys in .env files for the models 

## type the command "streamlit run streamlit_app.py" in your project terminal


