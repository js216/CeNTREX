import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, Event
from dash.dependencies import State as StateDash
import plotly.graph_objs as go
from calculate_levels import *
import pandas as pd
import os
import pickle

data_dir = 'DATA'
QN = np.load(data_dir+'/QN.npy')
# energies = np.load(data_dir+'/energies;Ez-0_70_71;Ex-0;Ey-0;Bx-0;By-0;Bz-18.4.npy')
# field = np.load(data_dir+'/field;Ez-0_70_71;Ex-0;Ey-0;Bx-0;By-0;Bz-18.4.npy')
# states_sorted = np.load(data_dir+'/states_sorted;Ez-0_70_71;Ex-0;Ey-0;Bx-0;By-0;Bz-18.4.npy')

app = dash.Dash()

def find_datafiles():
    fnames = []
    for file in os.listdir(data_dir):
        if file.startswith('energies'):
            fnames.append(os.path.join(data_dir, file))
    return fnames

def extract_params_datafiles(fnames):
    params = []
    for fname in fnames:
        fname = fname.strip('.npy')
        tmp = fname.split(';')
        tmp1 = tmp[1].split('-')[1].split('_')
        field_run = [tmp[1][:2], tmp1[0], tmp1[1], tmp1[2]]
        fields_cst = []
        for val in tmp[2:]:
            fields_cst.append(val.split('-'))
        params.append((field_run, fields_cst))
    return params

def generate_dropdown_files(fnames, params):
    options = []
    for idf, (fname, par) in enumerate(zip(fnames, params)):
        label = '{0}:{1}->{2}'.format(*par[0])
        for p in par[1]:
            label += '; {0}={1}'.format(*p)
        options.append({'label': label , 'value':idf})
    return dcc.Dropdown(options = options, id = 'file',
                        placeholder = 'select a file')

fnames = find_datafiles()
params = extract_params_datafiles(fnames)

def serve_layout():
    layout = html.Div([
        html.H1(children = 'TlF Levels'),
        html.Div([
        html.Div([
        html.Div([dcc.Dropdown(options = [{'label':'Ex', 'value':'Ex'}, {'label':'Ey', 'value':'Ey'},
                         {'label':'Ez', 'value':'Ez'}, {'label':'Bx', 'value':'Bx'},
                         {'label':'By', 'value':'By'}, {'label':'Bz', 'value':'Bz'}],
               id = 'field', placeholder = 'select a field')], style = {'width':'20%', 'display':'inline-block'}),
        html.Div([
               dcc.Input(
                   placeholder='fieldstart',
                   type='number',
                   id='fieldstart'
               ),
               dcc.Input(
                   placeholder='fieldstop',
                   type='number',
                   id='fieldstop'
               ),
               dcc.Input(
                   placeholder='fieldsteps',
                   type='number',
                   id='fieldsteps'
               )], style = {'width':'49%', 'display':'inline-block'}),
        html.Div([dcc.Input(
            placeholder='Ex',
            type='number',
            id='field1'
        ),
        dcc.Input(
            placeholder='Ey',
            type='number',
            id='field2'
        ),
        dcc.Input(
            placeholder='Bx',
            type='number',
            id='field3'
        ),
        dcc.Input(
            placeholder='By',
            type='number',
            id='field4'
        ),
        dcc.Input(
            placeholder='Bz',
            type='number',
            id='field5'
        )], id= 'fieldboxes'),
        html.Div([
        html.Button('Calculate', id='calculate')]),
        html.Div([dcc.Dropdown(options = [{'label':'J=0', 'value':0},
                                          {'label':'J=1', 'value':1},
                                          {'label':'J=2', 'value':2},
                                          {'label':'J=3', 'value':3},
                                          {'label':'J=4', 'value':4},
                                          {'label':'J=5', 'value':5}],
                               multi = False, id = 'Jselector', value = 1,
                               placeholder = 'J state selection')],
                               style = {'width':'16.7%'})], style = {'display':'table-cell'}),
        html.Div([generate_dropdown_files(fnames, params)], id = 'files',  style = {'width':'40%', 'display':'table-cell'})
        ]),
        html.Div(
        [
            dcc.Graph(id = 'graph_levels', style={'height': '80vh'}),

        ], style={'width': '49%', 'display': 'inline-block'}
        ),
        html.Div(
        [
            dcc.Graph(id = 'qnumbers', style={'height': '80vh'})
        ], style={'width': '49%', 'display': 'inline-block'}
        ),
        html.Div(id='calculate_signal', style={'display': 'none'}),
        html.Div(id='graph_range', style={'display': 'none'}),
        html.Div(id='file_loaded', style={'display': 'none'})
        ]
    )
    return layout

app.layout = serve_layout()

@app.callback(
    Output('fieldboxes', 'children'),
    [Input('field', 'value')])
def create_inputs(field):
    inputs = []
    fields = ['Ex', 'Ey', 'Ez', 'Bx', 'By', 'Bz']
    fields = [f for f in fields if f != field]
    for idx, f in enumerate(fields):
        inputs.append(dcc.Input(placeholder = f, id = 'field{0}'.format(idx+1), type = 'number'))
    return inputs

@app.callback(
    Output('files', 'children'),
    [Input('calculate_signal', 'children')])
def update_file_dropdown(calculates_signal):
    global fnames
    global params

    fnames = find_datafiles()
    params =  extract_params_datafiles(fnames)

    return generate_dropdown_files(fnames, params)


@app.callback(Output('file_loaded', 'children'), [Input('file', 'value')])
def load_file(file_number):
    if type(file_number) != type(None):
        global energies
        global field
        global states_sorted

        fname = fnames[file_number]
        energies = np.load(fname)
        field = np.load(fname.replace('energies', 'field'))
        states_sorted = np.load(fname.replace('energies', 'states_sorted'))

@app.callback(Output('calculate_signal','children' ), [Input('calculate', 'n_clicks')],
              [StateDash('field1', 'value'), StateDash('field2', 'value'),
              StateDash('field3', 'value'), StateDash('field4', 'value'),
              StateDash('field5', 'value'), StateDash('fieldstart', 'value'),
              StateDash('fieldstop', 'value'), StateDash('fieldsteps', 'value'),
              StateDash('field', 'value')])
def calculate_values(n_clicks, field1, field2, field3, field4, field5,
                     fieldstart, fieldstop, fieldsteps, fieldvary):
    if type(fieldstart) != type(None):
        global energies
        global field
        global states_sorted

        field = np.linspace(fieldstart, fieldstop, fieldsteps)
        fieldvals = [field1, field2, field3, field4, field5]
        fieldindices = {'Ex':0,'Ey':1,'Ez':2,'Bx':3, 'By':4, 'Bz':5}
        indicesfield = {v:k for k, v in fieldindices.items()}
        fields = []
        idv = 0
        for idx in range(6):
            if idx != fieldindices[fieldvary]:
                fields.append(np.ones(field.shape)*fieldvals[idv])
                idv += 1
            else:
                fields.append(field)

        Ex, Ey, Ez, Bx, By, Bz = fields
        energies, eigvecs = calculate_levels(Ex, Ey, Ez, Bx, By, Bz)
        states_sorted = state_sort(eigvecs, QN, epsilon=0.5)

        fname = data_dir+'/energies;{0}-{1}_{2}_{3}'.format(fieldvary, fieldstart, fieldstop, fieldsteps)
        idv = 0
        for idx in range(6):
            if idx != fieldindices[fieldvary]:
                fname += ';{0}-{1}'.format(indicesfield[idx], fieldvals[idv])
                idv += 1
        np.save(fname, energies)
        np.save(fname.replace('energies', 'field'), field)
        np.save(fname.replace('energies', 'eigvecs'), eigvecs)
        np.save(fname.replace('energies', 'states_sorted'), states_sorted)


def get_lrange(Jstate):
    default_level_range = (4,16)
    if (type(Jstate) == type(None)):
        lstart, lstop = default_level_range
    else:
        jlevels = lambda j: (2*j+1)*4 if j >= 0 else 0
        level_range = (np.sum([jlevels(j) for j in range(Jstate)]).astype(int),
                       np.sum([jlevels(j) for j in range(Jstate+1)]).astype(int))
    lstart, lstop = level_range
    return lstart, lstop

@app.callback(Output('graph_range','children' ),
              [Input('graph_levels', 'relayoutData')],
              [StateDash('graph_range', 'children')])
def update_graphbounds(graphdata, axisdata):
    xaxis = ['xaxis.range[0]', 'xaxis.range[1]']
    yaxis = ['yaxis.range[0]', 'yaxis.range[1]']

    print(graphdata)


def create_graph_levels(x,y,level):
    return go.Scatter(x=x, y=y, mode = 'markers+lines',
            name='level {0}'.format(level), marker={"size":3})

@app.callback(Output('graph_levels', 'figure'),
              [
               Input('calculate_signal', 'children'),
               Input('file_loaded', 'children'),
               Input('Jselector', 'value')])
def update_figure_levels(calculate_signal, file_loaded, Jstate):
    lstart, lstop = get_lrange(Jstate)

    data = []
    subtract = energies[:,lstart:lstop].mean()/1e3
    for idl, level in enumerate(range(lstart,lstop)):
        data.append( create_graph_levels(field, energies[:,level].T/1e3-subtract, idl+lstart) )
    return {'data': data, 'layout': go.Layout(
            xaxis={
                'title': 'E [V/cm]', 'showgrid':False,
            },
            yaxis={
                'title': 'Energy [kHz]','showgrid':False, 'zeroline':False
            },
            hovermode='closest')}

def create_table_qnumbers(df, level):

    fill = [['white']*len(df.level)]
    m = df.level.values == level
    m = list(m.nonzero()[0])
    for idc in m:
        fill[0][idc] = "#C2D4FF"
    # check degeneracy
    m = np.where(np.abs(df.energy.values - df.energy.values[m[0]]) < 1e-5)[0]
    for idc in m:
        if df.level.values[idc] != level:
            fill[0][idc] = '#ffc2d4'
    decimals = pd.Series([5,3,3], index = ['energy', 'amp_R', 'amp_I'])
    df = df.round(decimals)
    cells = [df.level.values, df.energy.values, df.amp_R.values,
             df.amp_I.values, df.J.values, df.mJ.values, df.m1.values,
             df.m2.values]

    return go.Table(header = dict(values=df.columns.values,
                                  fill = dict(color = '#cccccc')),
                    cells = dict(values=cells, fill = dict(color = fill)))

def check_curvenum(curve_number, lstart, lstop):
    r = lstop-lstart
    if curve_number > r:
        return 0
    else:
        return curve_number

def get_selected_curves(selected):
    if type(selected) != type(None):
        if len(selected) > 0:
            selected_curves = \
                np.unique([val['curveNumber'] for val in selected['points']])
            return selected_curves
    else:
        return None

@app.callback(Output('qnumbers', 'figure'),
    [Input('graph_levels', 'hoverData'),
     Input('file_loaded', 'children'),
     Input('Jselector', 'value'),
     Input('graph_levels', 'selectedData')]
     )
def update_table(hover, file_loaded, Jstate, selected):
    lstart, lstop = get_lrange(Jstate)

    if type(hover) == type(None):
        index = 0
        curve_number = 0
    else:
        index = hover['points'][0]['pointIndex']
        curve_number = hover['points'][0]['curveNumber']

    selected_levels = get_selected_curves(selected)
    if type(selected_levels) != type(None):
        indices = [val+lstart for val in selected_levels]
        if curve_number < min(selected_levels):
            curve_number = min(selected_levels)
        elif curve_number > max(selected_levels):
            curve_number = max(selected_levels)
    else:
        indices = list(range(lstart,lstop))


    curve_number = check_curvenum(curve_number, lstart, lstop)

    qnumbers = get_quantum_numbers_sort(states_sorted, index)
    qnumbers = [qnumbers[i] for i in indices]
    qnumbers_l = []
    for qns, energy in zip(qnumbers, energies[index,indices]):
        for qn in qns[1]:
            qndict = qn
            qndict['level'] = qns[0]
            qndict['energy'] = energy/1e3
            qnumbers_l.append(qndict)
    df = pd.DataFrame(qnumbers_l)
    df = df[['level', 'energy', 'amp_R', 'amp_I', 'J', 'mJ', 'm1', 'm2']]
    df.energy -= df.energy.min()
    df['amp'] = (df.amp_R**2+df.amp_I**2)
    df = df.sort_values(by = ['energy', 'amp'], ascending = [False, False]).drop('amp',1)
    table= create_table_qnumbers(df, curve_number+lstart)
    return {'data':[table]}

if __name__ == "__main__":
    app.run_server(debug = True)
    #app.run_server(host = '0.0.0.0', debug = True)
