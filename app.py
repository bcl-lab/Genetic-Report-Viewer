from flask import Flask, render_template
from auth import *

# we use this to shorten a long resource reference when displaying it
MAX_LINK_LEN = 20
# we only care about genomic stuff here


app = Flask(__name__)


def api_call(api_endpoint):
    '''
    helper function that makes API call 
    '''
    access_token = request.cookies['access_token']
    auth_header = {'Accept': 'application/json', 'Authorization': 'Bearer %s' % access_token}
    resp = requests.get('%s%s' % (API_BASE, api_endpoint), headers=auth_header)
    return resp.json()


def to_internal_id(id):
    '''
    markup an internal resource id with anchor tag.
    '''
    return '<a href="/reports/%s">%s...</a>' % (id, 'Genetics Report')


def render_fhir(resource):
    '''
    render a "nice" view of a FHIR bundle
    '''
    for entry in resource['entry']:
        entry['resource']['id'] = to_internal_id(entry['resource'].get('id', ''))
    return render_template('bundle_view.html', **resource)


@app.route('/')
@require_oauth
def index():
    return redirect('/resources/Patient')


# if the user authorize the app, use code to exchange access_token to the server
@app.route('/recv_redirect')
def recv_code():
    code = request.args['code']
    access_token = get_access_token(code)
    resp = redirect('/')
    resp.set_cookie('access_token', access_token)
    return resp


@app.route('/resources/<path:forwarded_url>')
@require_oauth
def forward_api(forwarded_url):
    forward_args = request.args.to_dict(flat=False)

    forward_args['_format'] = 'json'
    api_url = '/%s?%s'% (forwarded_url, urlencode(forward_args, doseq=True))
    bundle = api_call(api_url)
    # not bundle but plain resource
    if bundle.get('type') != 'searchset':
        resource = bundle
        bundle = {
            'resourceType': resource['resourceType'],
            'entry': [{
                'resource': resource,
                'id': forwarded_url
            }],
            'is_single_resource': True,
        }
    elif len(bundle.get('entry', [])) > 0:
        bundle['resourceType'] = bundle['entry'][0]['resource']['resourceType']

    return render_fhir(bundle)


@app.route('/reports/<path:id>')
def report_generate(id):
    '''
    fetch the instances of observationforgenetics profile, reportforgenetics profile, sequence resource of selected
    patient. Then select representative genetics info from these instances.
    '''
    # initiation
    source, gene, sequence_refs, obs_value, variation, coordinate, frequency, condition = [], [], [], [], [], [], [], []
    patient_count = api_call('/Patient?_format=json').get('total')
    # read the patient instance by id
    patient = api_call('/Patient/'+id+'?_format=json')
    # search all the observationforgenetics instance for this patient
    observations = api_call('/observationforgenetics?subject:Patient._id='+id+'&_format=json')
    total = observations.get('total')
    # search the reportforgenetics for this patient
    # in this demo app, we assume one patient only has one reportforgenetics instance
    diagnosticReports = api_call('/reportforgenetics?subject:Patient._id='+id+'&_format=json')
    variation_id = None

    report_extensions = diagnosticReports['entry'][0]['resource']['extension']
    for extension in report_extensions:
        if 'Condition' in extension['url']:
            condition_ref = extension['valueReference']['reference']
            condition_resource = api_call('/'+condition_ref+'?_format=json')
            condition.append(condition_resource['code'].get('text'))
    if len(condition)==0:
        condition.append('Unknown')

    for observation in observations['entry']:
        obs_value.append(observation['resource'].get('valueCodeableConcept')['text'])
        obs_extensions = observation['resource'].get('extension')
        for i in obs_extensions:
            if 'Source' in i['url']:
                source.append(i['valueCodeableConcept'].get('text'))
            elif 'Gene' in i['url']:
                gene.append(i['valueCodeableConcept'].get('text'))
            elif 'Sequence' in i['url']:
                sequence_refs.append(i['valueReference']['reference'])
            elif 'VariationId' in i['url']:
                variation_id = i['valueCodeableConcept'].get('coding')[0].get('code')

    for seq_reference in sequence_refs:
        sequence = api_call('/'+seq_reference+'?_format=json')
        if sequence['type'] not in 'DNA':
            continue
        variation.append("%s (observed allele/reference allele is %s/%s)" % (variation_id,
                                                                             sequence['variation']['observedAllele'],
                                                                             sequence['variation']['referenceAllele']))
        coordinate.append("%s : chrom %s (%s ~ %s)" % (sequence['referenceSeq'][0]['genomeBuild'].get('text'),
                                                       sequence['referenceSeq'][0]['chromosome'].get('text'),
                                                       sequence['variation']['start'],
                                                       sequence['variation']['end']))

        # search for all observationforgenetics instances containing this variant
        observations_for_this_variation = api_call('/observationforgenetics?Sequence.variationID='+variation_id+'&_format=json').get('entry')
        subject_id = []
        # collect all patient having this variant
        for entry in observations_for_this_variation:
            id = entry['resource'].get('subject')
            if id and id not in subject_id:
                subject_id.append(id)
        # calculate frequency
        each_frequency = float(len(subject_id))/patient_count
        frequency.append(each_frequency)

    # selected info
    patient_info = {
                    'name': patient['name'][0]['text'],
                    'gender': patient['gender'],
                    'id': patient['id'],
                    'source': source,
                    'gene': gene,
                    'variation': variation,
                    'coordinate': coordinate,
                    'total': total,
                    'status': obs_value,
                    'condition': condition,
                    'frequency': frequency
                    }

    return render_template('patient_info_view.html', **patient_info)


if __name__ == '__main__':
    app.run(debug=True, port=8000)
