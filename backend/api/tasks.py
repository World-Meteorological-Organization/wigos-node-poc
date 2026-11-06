from django.tasks import task


@task
def publish_to_wis2(wmdrv2):
    """Publish the station to WIS2"""
    # Implement the publishing logic here
    print(f"Publishing station to WIS2: {wmdrv2}")


    # step 1
    # write record to minio. Get filename

    # step 2
    # create WNM 

    # step 3
    # publish WNM on mosquito