from plotly.utils import PlotlyJSONEncoder
import plotly.graph_objects as go
from webservice import db, dbModels
from utils import stringTools
import datetime
import json

timedelta = datetime.timedelta(weeks=4)

def get_latest_stars_before_deadline(ont : dbModels.Ontology, deadline):
    sorted_versions = sorted([v for v in ont.versions], key=lambda v: v.version, reverse=True)
    for version in sorted_versions:
        if version.version < deadline:
            return version.stars

    return None

def group_by_stars():
    dates = generate_dates()
    results = {}
    

    for deadline in dates:
        y_vals = {}
        # start with 0 stars each
        for i in range(5):
            y_vals[i] = 0
        for ont in db.session.query(dbModels.OfficialOntology).all():
            stars = get_latest_stars_before_deadline(ont, deadline)
            if stars != None:
                y_vals[stars] = y_vals.get(stars, 0) + 1
        results[deadline] = y_vals
    return dates, results

def generate_dates():
    day = datetime.datetime.now()
    dates = []
    for i in range(7):
        dates.append(day)
        day = day - timedelta

    dates.reverse()
    return dates

def generate_star_graph():
    x_vals, results = group_by_stars()
    traces = []

    # zero stars:
    traces.append(
            go.Scatter(
                x=x_vals,
                y=[results[d][0] for d in x_vals],
                name=stringTools.generateStarString(0),
                stackgroup='one',
                line=dict(width=0.5, color='rgb(255, 0, 0)'),
            )
        )
    # one star:
    traces.append(
            go.Scatter(
                x=x_vals,
                y=[results[d][1] for d in x_vals],
                name=stringTools.generateStarString(1),
                stackgroup='one',
                line=dict(width=0.5, color='rgb(255, 165, 0)'),
            )
        )
    # two stars:
    traces.append(
            go.Scatter(
                x=x_vals,
                y=[results[d][2] for d in x_vals],
                name=stringTools.generateStarString(2),
                stackgroup='one',
                line=dict(width=0.5, color='rgb(255, 215, 0)'),
            )
        )
    # three stars:
    traces.append(
            go.Scatter(
                x=x_vals,
                y=[results[d][3] for d in x_vals],
                name=stringTools.generateStarString(3),
                stackgroup='one',
                line=dict(width=0.5, color='rgb(124, 252, 0)'),
            )
        )
    # four stars:
    traces.append(
            go.Scatter(
                x=x_vals,
                y=[results[d][4] for d in x_vals],
                name=stringTools.generateStarString(4),
                stackgroup='one',
                line=dict(width=0.5, color='rgb(34, 139, 34)'),
            )
        )
    # All onts
    traces.append(
        go.Scatter(
            x=x_vals,
            y=[sum([star_count for star_count in results[d].values()]) for d in x_vals],
            name='All Ontologies',
            line=dict(width=0.5, color='rgb(0, 0, 0)'),
        )
    )
    with open('./stats/stars_over_time.json', 'w+') as json_file:
        json.dump(traces , json_file, cls=PlotlyJSONEncoder, indent=4)

