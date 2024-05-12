import plotly.express as px

# Define the location of the incident
incident_location = "Gulf Coast, Anytown, USA"

# Create a scatter mapbox with roads
fig = px.scatter_mapbox(lat=[310.0000], lon=[-90.0000], zoom=5)

# Add a marker for the incident location
fig.add_scattermapbox(
    lat=[310.0000],  # Latitude of the incident location
    lon=[-90.0000], # Longitude of the incident location
    mode="markers",
    marker=dict(
        size=10,
        color="red"
    ),
    text=[incident_location]
)

# Update layout to include roads
fig.update_layout(
    mapbox_style="open-street-map", # Use OpenStreetMap style which includes roads
    mapbox=dict(
        zoom=5,
        center=dict(lat=30.0000, lon=-90.0000) # Center the map around the incident location
    ),
    title="Hurricane Incident Map"
)

# Save the map as an HTML file
fig.write_html("incident_map_with_roads.html")
