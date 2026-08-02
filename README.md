# RNMS — Core MVP (नगर पंचायत रतसर कलां वित्त एवं निर्माण कार्य प्रबंधन पोर्टल)

यह RNMS स्पेसिफिकेशन के मुख्य प्रवाह का काम करने वाला MVP है:
**मद/GO → आय/किस्त → कार्य → टेंडर/वर्क ऑर्डर → बिल → भुगतान अनुमोदन (Operator→Accountant→EO→Post) → कैशबुक**

## Tech Stack
- Python + Flask (server-rendered, Jinja2 templates, Bootstrap 5 for UI)
- PostgreSQL (production, Render) / SQLite (local विकास — बिना किसी एक्स्ट्रा इंस्टॉल के तुरंत चलता है)

## Local चलाना
```bash
pip install flask   # पहले से हो तो जरूरत नहीं
python3 app.py       # http://localhost:5050 पर खुलेगा
```
पहली बार चलाने पर अपने-आप SQLite डेटाबेस बन जाएगा (`rnms_dev.db`) और यह डिफ़ॉल्ट लॉगिन बन जाएँगे:

| Username   | Password   | भूमिका           |
|------------|------------|------------------|
| admin      | admin123   | Admin            |
| eo         | eo123      | EO/Admin         |
| accountant | acc123     | Accountant       |
| operator   | op123      | Account Operator |

**लाइव करने से पहले ये पासवर्ड ज़रूर बदलें।**

## Render पर Deploy
1. इस फ़ोल्डर को GitHub रिपॉज़िटरी में पुश करें।
2. Render पर नया **Blueprint** बनाएँ और यह रिपॉज़िटरी चुनें — `render.yaml` में web service + PostgreSQL डेटाबेस दोनों पहले से परिभाषित हैं।
3. Deploy होते ही `DATABASE_URL` अपने-आप PostgreSQL से जुड़ जाएगा (कोड में `db.py` इसे पहचान कर SQLite की जगह PostgreSQL इस्तेमाल करता है)।
4. पहली बार ऐप चलते ही स्कीमा एवं डिफ़ॉल्ट users अपने-आप बन जाएँगे (`bootstrap()` फ़ंक्शन)।

## अभी इसमें क्या शामिल है (Core MVP)
- Login + 4 भूमिकाएँ (RBAC)
- Masters: मद, वार्ड, वित्तीय वर्ष, परिसंपत्ति प्रकार, फर्म, बैंक खाता
- वित्त/आय: आरम्भिक अवशेष, GO रजिस्टर, किस्तें, बैंक ब्याज, बैंक चार्ज/वापसी
- कार्य/टेंडर: कार्य प्रस्ताव (Auto Work ID), टेंडर, Work Order
- बिल/भुगतान: GST गणना, कटौती (CGST/SGST/Income Tax/Labour Cess), 4-चरण अनुमोदन
- Auto-generated Cashbook (running balance सहित)
- मदवार Fund Summary डैशबोर्ड

## अभी शामिल नहीं (Phase 2 — अगला चरण)
DMS/दस्तावेज़ अपलोड, Security Deposit, Agreement, Legacy Work विवरण, Vishwakarma/BM-15, Monthly/Yearly Closing, Bank Reconciliation, Failed Payment/Re-payment, Excel/PDF Export, पूर्ण Audit Log।
पूरे 37-टेबल डिज़ाइन के लिए साथ में दी गई `RNMS_Database_Schema.sql` एवं डिज़ाइन दस्तावेज़ देखें — इसी बुनियाद पर आगे जोड़ा जा सकता है।
