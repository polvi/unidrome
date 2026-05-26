from openai import OpenAI
import geopandas as gpd
import pandas as pd
from shapely import wkt
import pprint

client = OpenAI()

def conflate(df):
    system_prompt = """
Your goal is to conflate airport data from a few related rows into a json object per distinct aerodrome. It's possible you will be given data about multiple airports and you need to return multiple json objects. Most of the time you'll be given multiple rows about a single airport, and you'll need to pick which data to use. Do not duplicate results for airports that are related. For instance, Bob Hope Airport and Hollywood Burbank are the same airport and should only return one result.  Do not make up a field, instead pick one of the given fields and site the source in the object you return. If a return value is unknown, you will return "null" for the field and source. You will output an array of json objects containing the following information:
{
    results: [ // a list of the airports found in the data provided with the following fields, only returning results that relate to different distinct airports. For example, Bob Hope and Burbank Hollywood would only return one result. 
        {
          "airport_name": "Name of the airport",
          "airport_name:source": "The key that was used to generate the source",
          "city": "City where the airport is located",
          "city:source": "The key that was used to generate the source",
          "state": "State where the airport is located",
          "state:source": "The key that was used to generate the source",
          "elev": "Elevation of the airport in feet"
          "elev:source": "The key that was used to generate the source",
          "latitude_decimal": "The latitude in decimal form",
          "latitude_decimal:source": "The key that was used to generate the source",
          "longitude_decimal": "The longitude in decimal form",
          "longitude_decimal:source": "The key that was used to generate the source",
        }
    ]
}
"""

    messages = [
            {
                "role": "system",
                "content": system_prompt
            }
    ]
    for _, row in df.iterrows():
        messages.append({
            "role": "user",
            "content": str(row.to_dict())
        })
    pprint.pp(messages)

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0.1,
        # This is to enable JSON mode, making sure responses are valid json objects
        response_format={
            "type": "json_object"
        },
        messages=messages
    )
    print(response.choices[0].message.content)
    

df = pd.read_csv("data/combined.csv", low_memory=False)
#df = df[df["world_ourairports_airports_type"] != "closed"]
#df = df[df["world_osm_daylight_aerodrome_name"].notnull()]
# df = df[df["h3_07"] == "8729a565bffffff"] LAX
#df[:10].groupby("h3_07", group_keys=False).apply(conflate)
df.groupby("h3_07", group_keys=False).apply(conflate)


# AI gets used when it's not FAA
# When there is more than one row of data in the h3

