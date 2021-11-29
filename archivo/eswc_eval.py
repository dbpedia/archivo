from webservice import db, dbModels
from datetime import datetime

def get_official_onts():
    return db.session.query(dbModels.OfficialOntology).all()

def get_sorted_diff_fallout(remove_dev=True):

    q = db.session.query(dbModels.Fallout).filter_by(inArchivo=True)
    if remove_dev:
        return (
            q.filter(dbModels.Fallout.source != "DEV")
            .order_by(dbModels.Fallout.date)
            .all()
        )
    else:
        return q.order_by(dbModels.Fallout.date).all()


def get_ont_index_mapping():

    official_onts = db.session.query(dbModels.OfficialOntology).all()
    result_map = {}
    for i, ont in enumerate(official_onts):
        result_map[ont.uri] = i

    return result_map


def uri_ont_mapping():

    all_official_onts = db.session.query(dbModels.OfficialOntology).all()

    ontmap = {}

    for ont in all_official_onts:
        ontmap[ont.uri] = ont

    return ontmap


def generate_fallout_dates(bad_days=list(), filter_fun=None):

    fallout = get_sorted_diff_fallout()

    dates = []

    for f in fallout:
        new_date = datetime(f.date.year, f.date.month, f.date.day)
        if new_date in bad_days:
            continue
        if filter_fun is not None and filter_fun(f):
            continue
        if new_date not in dates:
            dates.append(new_date)

    return dates


def check_if_ont_was_disabled_on_day(date, ont_fallout):

    fallout_on_day = [
        f.date
        for f in ont_fallout
        if date.year == f.date.year
        and date.month == f.date.month
        and date.day == f.date.day
    ]

    return len(fallout_on_day)


def get_downtimes_of_onts(bad_days=list()):

    ontmap = uri_ont_mapping()

    fallout = get_sorted_diff_fallout()

    dates = generate_fallout_dates(bad_days=bad_days)

    uri_downtimes_mapping = {}

    for uri in ontmap:

        ont_fallout = [f for f in fallout if f.ontology == uri]

        counter = 0

        downtimes = []

        for day in dates:
            fallouts_on_day = check_if_ont_was_disabled_on_day(day, ont_fallout)

            if fallouts_on_day == 0:
                if counter > 0:
                    downtimes.append(counter)
                counter = 0
            else:
                counter += 1

        # add last counter
        if counter > 0:
            downtimes.append(counter)

        uri_downtimes_mapping[uri] = sorted(downtimes)

    return uri_downtimes_mapping


def group_fallout_and_count(fallout, filter_fun=None):

    last_fallout_date_id = fallout[0].date

    failed_onts = []

    results = []

    for fallout_obj in fallout:

        if filter_fun(fallout_obj):
            continue

        if fallout_obj.uri == "http://xmlns.com/foaf/0.1/":
            error = fallout_obj.error.replace("\n", ";").replace(",", ";")
            print(f"{fallout_obj.date},{error}")

        timedelta = fallout_obj.date - last_fallout_date_id

        if timedelta.seconds > 7200:
            last_fallout_date_id = fallout_obj.date
            results.append((str(last_fallout_date_id), len(failed_onts)))
            failed_onts = []
        else:
            failed_onts.append(fallout_obj.uri)
    return results


def better_grouping_and_counting(fallout, filter_fun=None):

    last_fallout_date_id = fallout[0].date

    last_ont_index = 0

    ont_index_mapping = get_ont_index_mapping()

    failed_onts = []

    results = []

    for fallout_obj in fallout:

        if filter_fun(fallout_obj):
            continue

        try:
            new_index = ont_index_mapping[fallout_obj.ontology]
        except KeyError as k_error:
            print(f"Error for ont: {fallout_obj.ontology}")
            new_index = last_ont_index

        if new_index < last_ont_index:
            last_fallout_date_id = fallout_obj.date
            results.append((last_fallout_date_id, len(failed_onts)))
            last_ont_index = 0
            failed_onts = []
        else:
            failed_onts.append(fallout_obj.uri)
            last_ont_index = new_index
    return results


def check_counting(lst):

    counter = 0

    last_date = lst[0][0]

    for date, cnt in lst:
        if date.day == last_date.day:
            counter = counter + 1
        else:
            if counter != 3:
                print(f"Error on date {last_date}: Number of runs {counter}")
            counter = 1
            last_date = date


def get_fallout_onts_of_time(beginning, ending, filterfun=None):

    from sqlalchemy import and_

    new_fallout = (
        db.session.query(dbModels.Fallout)
        .filter_by(inArchivo=True)
        .filter(and_(dbModels.Fallout.date > beginning, dbModels.Fallout.date < ending))
        .order_by(dbModels.Fallout.date)
        .all()
    )

    if filterfun is not None:
        return [fo for fo in new_fallout if not filterfun(fo)]
    else:
        return new_fallout


def write_timelines(filename, bad_days=list()):

    import csv

    dates = generate_fallout_dates(bad_days=bad_days)

    ont_uris = [o.uri for o in get_official_onts()]

    fallout = get_sorted_diff_fallout()

    with open(filename, "w+") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Ont"] + [date.strftime("%Y-%m-%d") for date in dates])
        for ont_uri in ont_uris:
            print(f"[{datetime.now()}] Processing ont: {ont_uri}")
            ont_down = []
            for date in dates:
                ont_fallout = [f for f in fallout if f.ontology == ont_uri]
                ont_down_counter = check_if_ont_was_disabled_on_day(date, ont_fallout)
                if ont_down_counter == 0:
                    ont_down.append(None)
                else:
                    ont_down.append(ont_down_counter)
            writer.writerow([ont_uri] + ont_down)

# unstable -> on off ontology
# unreliable ->
# SPECIAL CASE: unavailable -> doesnt come back on (for one month)


if __name__ == "__main__":

    import csv
    from sqlalchemy import distinct

    # print(len(db.session.query(distinct(dbModels.Fallout.ontology)).filter(dbModels.Fallout.source != "DEV").all()))

    def remove_dev_onts(fallout_obj):
        if fallout_obj.source == "DEV" or "INTERNAL ERROR" in fallout_obj.error:
            return True
        else:
            return False

    bad_days = [datetime(2021, 8, 26), datetime(2021, 9, 5)]

    write_timelines("./timelines.csv", bad_days=bad_days)

    # uri_downtime_mapping = get_downtimes_of_onts(bad_days=bad_days)

    # with open("./min_max_downtime.csv", "w+") as csvfile:
    #     writer = csv.writer(csvfile)
    #     writer.writerow(("Ontology", "MinDowntime", "MaxDowntime", "CountDowntimes", "AvgDowntime"))

    #     for uri, downtimes in uri_downtime_mapping.items():
    #         print(f"{uri};{downtimes}")
    #         if len(downtimes) == 0:
    #             writer.writerow((uri, 0, 0))
    #         else:
    #             writer.writerow((uri, downtimes[0], downtimes[-1], len(downtimes), sum(downtimes)/len(downtimes)))

    # fallout = get_sorted_diff_fallout()
    # res = better_grouping_and_counting(fallout, filter_fun=remove_dev_onts)

    # check_counting(res)

    # with open("./counting_fallout.csv", "w+") as csvfile:
    #     writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
    #     writer.writerows(res)
    # begin_low = datetime(2021, 4, 13)
    # end_low = datetime(2021, 5, 10)
    # low_fallout = get_fallout_onts_of_time(
    #     begin_low, end_low, filterfun=remove_dev_onts
    # )
    # low_fallout_uris = set([fo.uri for fo in low_fallout])

    # begin_high = datetime(2021, 10, 29)
    # end_high = datetime(2021, 11, 10)
    # high_fallout = get_fallout_onts_of_time(
    #     begin_high, end_high, filterfun=remove_dev_onts
    # )
    # high_fallout_uris = set([fo.uri for fo in high_fallout])

    # begin_avg = datetime(2021, 5, 11)
    # end_avg = datetime(2021, 6, 12)
    # avg_fallout = get_fallout_onts_of_time(
    #     begin_avg, end_avg, filterfun=remove_dev_onts
    # )
    # avg_fallout_uris = set([fo.uri for fo in avg_fallout])

    # print("The average without the low fallout:")
    # print("\n".join(avg_fallout_uris - low_fallout_uris))
    # print("\n\n")
    # print("The high without the average:")
    # print("\n".join(high_fallout_uris - avg_fallout_uris))
