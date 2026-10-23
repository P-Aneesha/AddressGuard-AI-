# Reference data for address validation. Not exhaustive — representative coverage.

INDIAN_STATES = [
    "Telangana","Andhra Pradesh","Karnataka","Maharashtra","Tamil Nadu","Delhi",
    "West Bengal","Kerala","Rajasthan","Gujarat","Uttar Pradesh","Punjab","Haryana",
    "Bihar","Madhya Pradesh","Odisha","Assam","Jharkhand","Chhattisgarh","Goa",
    "Uttarakhand","Himachal Pradesh","Puducherry","Chandigarh","Jammu and Kashmir"
]

# alias/misspelling -> canonical state
STATE_ALIASES = {
    "telangana":"Telangana","telengana":"Telangana","telangna":"Telangana","telagana":"Telangana",
    "karnataka":"Karnataka","karnatka":"Karnataka","karnatak":"Karnataka","karntaka":"Karnataka",
    "maharashtra":"Maharashtra","maharastra":"Maharashtra","maharashta":"Maharashtra",
    "tamil nadu":"Tamil Nadu","tamilnadu":"Tamil Nadu","tamil nad":"Tamil Nadu",
    "west bengal":"West Bengal","westbengal":"West Bengal","w bengal":"West Bengal",
    "kerala":"Kerala","kerela":"Kerala","keral":"Kerala",
    "rajasthan":"Rajasthan","rajisthan":"Rajasthan","rajasthhan":"Rajasthan",
    "gujarat":"Gujarat","gujrat":"Gujarat","gujarath":"Gujarat",
    "andhra pradesh":"Andhra Pradesh","andhrapradesh":"Andhra Pradesh","andhra":"Andhra Pradesh",
    "uttar pradesh":"Uttar Pradesh","uttarpradesh":"Uttar Pradesh","up":"Uttar Pradesh",
    "delhi":"Delhi","new delhi":"Delhi","dilli":"Delhi",
    "punjab":"Punjab","panjab":"Punjab",
    "haryana":"Haryana","harayana":"Haryana",
    "bihar":"Bihar","bihaar":"Bihar",
    "madhya pradesh":"Madhya Pradesh","madhyapradesh":"Madhya Pradesh","mp":"Madhya Pradesh",
    "odisha":"Odisha","orissa":"Odisha",
    "assam":"Assam","asam":"Assam",
    "jharkhand":"Jharkhand","jharkand":"Jharkhand",
    "chhattisgarh":"Chhattisgarh","chattisgarh":"Chhattisgarh",
    "goa":"Goa",
    "uttarakhand":"Uttarakhand","uttaranchal":"Uttarakhand",
    "himachal pradesh":"Himachal Pradesh","himachalpradesh":"Himachal Pradesh",
    "puducherry":"Puducherry","pondicherry":"Puducherry",
    "chandigarh":"Chandigarh",
    "jammu and kashmir":"Jammu and Kashmir","jammu kashmir":"Jammu and Kashmir","j&k":"Jammu and Kashmir",
}

# city -> state (canonical)
CITY_STATE_MAP = {
    "Hyderabad":"Telangana","Warangal":"Telangana","Karimnagar":"Telangana","Nizamabad":"Telangana",
    "Vijayawada":"Andhra Pradesh","Visakhapatnam":"Andhra Pradesh","Guntur":"Andhra Pradesh","Tirupati":"Andhra Pradesh",
    "Bengaluru":"Karnataka","Mysuru":"Karnataka","Mangaluru":"Karnataka","Hubballi":"Karnataka",
    "Mumbai":"Maharashtra","Pune":"Maharashtra","Nagpur":"Maharashtra","Nashik":"Maharashtra","Thane":"Maharashtra",
    "Chennai":"Tamil Nadu","Coimbatore":"Tamil Nadu","Madurai":"Tamil Nadu","Trichy":"Tamil Nadu",
    "Delhi":"Delhi","New Delhi":"Delhi",
    "Kolkata":"West Bengal","Howrah":"West Bengal","Siliguri":"West Bengal",
    "Kochi":"Kerala","Thiruvananthapuram":"Kerala","Kozhikode":"Kerala","Kollam":"Kerala",
    "Jaipur":"Rajasthan","Jodhpur":"Rajasthan","Udaipur":"Rajasthan","Kota":"Rajasthan",
    "Ahmedabad":"Gujarat","Surat":"Gujarat","Vadodara":"Gujarat","Rajkot":"Gujarat",
    "Lucknow":"Uttar Pradesh","Kanpur":"Uttar Pradesh","Noida":"Uttar Pradesh","Agra":"Uttar Pradesh","Varanasi":"Uttar Pradesh",
    "Chandigarh":"Chandigarh","Amritsar":"Punjab","Ludhiana":"Punjab",
    "Gurugram":"Haryana","Faridabad":"Haryana",
    "Patna":"Bihar","Gaya":"Bihar",
    "Bhopal":"Madhya Pradesh","Indore":"Madhya Pradesh","Jabalpur":"Madhya Pradesh",
    "Bhubaneswar":"Odisha","Cuttack":"Odisha",
    "Guwahati":"Assam",
    "Ranchi":"Jharkhand","Jamshedpur":"Jharkhand",
    "Raipur":"Chhattisgarh",
    "Panaji":"Goa",
    "Dehradun":"Uttarakhand",
    "Shimla":"Himachal Pradesh",
}

# alias/misspelling -> canonical city
CITY_ALIASES = {
    "hydrabad":"Hyderabad","hyderbad":"Hyderabad","hyderabaad":"Hyderabad","hyd":"Hyderabad",
    "bangaluru":"Bengaluru","bangalor":"Bengaluru","bangalore":"Bengaluru","banglore":"Bengaluru","blr":"Bengaluru",
    "bombay":"Mumbai","mumbay":"Mumbai",
    "madras":"Chennai","chenai":"Chennai",
    "calcutta":"Kolkata","kolkatta":"Kolkata",
    "vizag":"Visakhapatnam","vishakapatnam":"Visakhapatnam",
    "mysore":"Mysuru","mangalore":"Mangaluru","hubli":"Hubballi",
    "pondicherry":"Puducherry",
    "cochin":"Kochi","trivandrum":"Thiruvananthapuram",
    "gurgaon":"Gurugram",
    "vadodra":"Vadodara","baroda":"Vadodara",
    "trichy":"Trichy","madurai":"Madurai",
}

# locality -> parent city (representative, not exhaustive)
KNOWN_LOCALITIES = {
    "Madhapur":"Hyderabad","Kondapur":"Hyderabad","Gachibowli":"Hyderabad","Banjara Hills":"Hyderabad",
    "Jubilee Hills":"Hyderabad","Ameerpet":"Hyderabad","Kukatpally":"Hyderabad","Begumpet":"Hyderabad",
    "Koramangala":"Bengaluru","Indiranagar":"Bengaluru","Whitefield":"Bengaluru","HSR Layout":"Bengaluru",
    "Jayanagar":"Bengaluru","Electronic City":"Bengaluru","Marathahalli":"Bengaluru",
    "Andheri":"Mumbai","Andheri West":"Mumbai","Bandra":"Mumbai","Powai":"Mumbai","Dadar":"Mumbai","Worli":"Mumbai",
    "T Nagar":"Chennai","Adyar":"Chennai","Velachery":"Chennai","Anna Nagar":"Chennai",
    "Salt Lake":"Kolkata","Park Street":"Kolkata","Ballygunge":"Kolkata",
    "Connaught Place":"Delhi","Dwarka":"Delhi","Rohini":"Delhi","Saket":"Delhi","Green Park":"New Delhi","Hauz Khas":"New Delhi",
    "Kothrud":"Pune","Hinjewadi":"Pune","Viman Nagar":"Pune","Shivajinagar":"Pune","FC Road":"Pune",
}

# alias/misspelling -> canonical locality
LOCALITY_ALIASES = {
    "kormangla":"Koramangala","koramangla":"Koramangala","korangla":"Koramangala",
    "indranagar":"Indiranagar","indiranagr":"Indiranagar",
    "madhapoor":"Madhapur","madhapur":"Madhapur",
    "kondapoor":"Kondapur",
    "gachibawli":"Gachibowli","shivaji nagar":"Shivajinagar","shivajinagr":"Shivajinagar","andheri west":"Andheri West","greenpark":"Green Park","t nagar":"T Nagar",
}

# PIN reference data. Prefixes are only broad regional hints; exact mappings
# below take precedence for known post-office PINs used by the application tests.
PIN_PREFIX_TO_STATE = {
    "50":"Telangana", "51":"Andhra Pradesh", "52":"Andhra Pradesh", "53":"Andhra Pradesh",
    "56":"Karnataka", "57":"Karnataka", "58":"Karnataka", "59":"Karnataka",
    "40":"Maharashtra", "41":"Maharashtra", "42":"Maharashtra", "43":"Maharashtra", "44":"Maharashtra",
    "60":"Tamil Nadu", "61":"Tamil Nadu", "62":"Tamil Nadu", "63":"Tamil Nadu", "64":"Tamil Nadu",
    "11":"Delhi",
    "70":"West Bengal", "71":"West Bengal", "72":"West Bengal", "73":"West Bengal", "74":"West Bengal",
    "67":"Kerala", "68":"Kerala", "69":"Kerala",
    "30":"Rajasthan", "31":"Rajasthan", "32":"Rajasthan", "33":"Rajasthan", "34":"Rajasthan",
    "38":"Gujarat", "39":"Gujarat", "36":"Gujarat", "37":"Gujarat",
    "20":"Uttar Pradesh", "21":"Uttar Pradesh", "22":"Uttar Pradesh", "23":"Uttar Pradesh",
    "24":"Uttar Pradesh", "25":"Uttar Pradesh", "26":"Uttar Pradesh", "27":"Uttar Pradesh", "28":"Uttar Pradesh",
    "14":"Punjab", "15":"Punjab", "16":"Haryana", "12":"Haryana", "13":"Haryana",
    "80":"Bihar", "81":"Bihar", "82":"Bihar", "83":"Bihar",
    "45":"Madhya Pradesh", "46":"Madhya Pradesh", "47":"Madhya Pradesh", "48":"Madhya Pradesh",
    "75":"Odisha", "76":"Odisha", "77":"Odisha", "78":"Assam",
    "49":"Chhattisgarh", "17":"Himachal Pradesh",
}

# Exact PIN -> state/city/locality reference entries. These override the broad
# prefix map and prevent false conflicts caused by ambiguous prefix ranges.
PIN_REFERENCE = {
    "500034": {"state": "Telangana", "city": "Hyderabad", "locality": "Banjara Hills"},
    "500032": {"state": "Telangana", "city": "Hyderabad", "locality": "Gachibowli"},
    "500033": {"state": "Telangana", "city": "Hyderabad", "locality": "Jubilee Hills"},
    "500038": {"state": "Telangana", "city": "Hyderabad", "locality": "Vengal Rao Nagar"},
    "500075": {"state": "Telangana", "city": "Hyderabad", "localities": ["Himayatnagar", "Gandipet", "Kokapet"]},
    "500081": {"state": "Telangana", "city": "Hyderabad", "locality": "Madhapur"},
    "560038": {"state": "Karnataka", "city": "Bengaluru", "locality": "Indiranagar"},
    "560034": {"state": "Karnataka", "city": "Bengaluru", "locality": "Koramangala"},
    "400053": {"state": "Maharashtra", "city": "Mumbai", "localities": ["Andheri West", "Andheri"]},
    "411005": {"state": "Maharashtra", "city": "Pune", "locality": "Shivajinagar"},
    "110001": {"state": "Delhi", "city": "New Delhi", "locality": "Connaught Place"},
    "110016": {"state": "Delhi", "city": "New Delhi", "localities": ["Hauz Khas", "Green Park"]},
    "600017": {"state": "Tamil Nadu", "city": "Chennai", "locality": "T Nagar"},
}

STREET_KEYWORDS = ["road","street","st","lane","ln","nagar","colony","main","cross","layout",
                    "marg","avenue","circle","chowk","sector","phase","block","extension","ext",
                    "salai","gali"]

HOUSE_KEYWORDS = ["h.no","h no","hno","house no","house number","door no","d.no","plot no","plot"]
FLAT_KEYWORDS = ["flat","apt","apartment no","unit","suite","room no","#"]
BUILDING_KEYWORDS = ["apartments","apartment","towers","tower","residency","heights","hights",
                      "enclave","complex","chambers","plaza","arcade","court","gardens","homes",
                      "villa","villas","society","chs","nivas","nilayam","bhavan","sadan","mansion"]

ADDRESS_CATEGORY_TERMS = {
    "house": HOUSE_KEYWORDS, "flat": FLAT_KEYWORDS, "building": BUILDING_KEYWORDS, "street": STREET_KEYWORDS
}

ABBREVIATION_EXPANSIONS = {
    "rd":"Road","st":"Street","ln":"Lane","apt":"Apartment","appt":"Apartment","nr":"Near",
    "opp":"Opposite","colny":"Colony","extn":"Extension","ext":"Extension","blk":"Block",
    "sec":"Sector","ph":"Phase","hno":"H.No","h.no":"H.No","no":"No","flr":"Floor",
    "mkt":"Market","stn":"Station","junc":"Junction",
}
