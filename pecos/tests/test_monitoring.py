import unittest
from nose.tools import *
from os.path import abspath, dirname, join
import pecos
import pandas as pd
from pandas import Timestamp, RangeIndex
from pandas.util.testing import assert_frame_equal
import numpy as np
from numpy import array

#pd.set_option('expand_frame_repr', False)

testdir = dirname(abspath(__file__))
datadir = join(testdir,'data')
simpleexampledir = join(testdir,'..', '..', 'examples','simple')

def simple_example_run_analysis(df):

    # Create an PerformanceMonitoring instance
    pm = pecos.monitoring.PerformanceMonitoring()

    # Populate the PerformanceMonitoring instance
    pm.add_dataframe(df)
    pm.add_translation_dictionary({'Wave': ['C','D']}) # group C and D

    # Check timestamp
    pm.check_timestamp(900)

    # Generate time filter
    clock_time = pecos.utils.datetime_to_clocktime(pm.df.index)
    time_filter = pd.Series((clock_time > 3*3600) & (clock_time < 21*3600), 
                        index=pm.df.index)
    pm.add_time_filter(time_filter)

    # Check missing
    pm.check_missing()

    # Check corrupt
    pm.check_corrupt([-999]) 

    # Add a composite signal which compares measurements to a model
    wave_model = np.array(np.sin(10*clock_time/86400))
    wave_measurments = pm.df[pm.trans['Wave']]
    wave_error = np.abs(wave_measurments.subtract(wave_model,axis=0))
    wave_error.columns=['Wave Error C', 'Wave Error D']
    pm.add_dataframe(wave_error)
    pm.add_translation_dictionary({'Wave Error': ['Wave Error C', 'Wave Error D']})
    
    # Check data for expected ranges
    pm.check_range([0, 1], 'B')
    pm.check_range([-1, 1], 'Wave')
    pm.check_range([None, 0.25], 'Wave Error')
    
    # Check for stagnant data within a 1 hour moving window
    pm.check_delta([0.0001, None], 'A', 3600) 
    pm.check_delta([0.0001, None], 'B', 3600) 
    pm.check_delta([0.0001, None], 'Wave', 3600) 
        
    # Check for abrupt changes between consecutive time steps
    pm.check_increment([None, 0.6], 'Wave') 
    
    # Compute the quality control index for A, B, C, and D
    mask = pm.mask[['A','B','C','D']]
    QCI = pecos.metrics.qci(mask, pm.tfilter)

    # Write test results
    pecos.io.write_test_results(pm.test_results)

    return QCI

class Test_simple_example(unittest.TestCase):

    @classmethod
    def setUp(self):
        trans = {
            'Linear': ['A'],
            'Random': ['B'],
            'Wave': ['C','D']}

        file_name = join(simpleexampledir,'simple.xlsx')

        self.raw_data = pd.read_excel(file_name, index_col=0)
        self.pm = pecos.monitoring.PerformanceMonitoring()
        self.pm.add_dataframe(self.raw_data)
        self.pm.add_translation_dictionary(trans)
        self.pm.check_timestamp(900)
        clocktime = pecos.utils.datetime_to_clocktime(self.pm.df.index)
        time_filter = (clocktime > 3*3600) & (clocktime < 21*3600)
        self.time_filter = pd.Series(time_filter, index=self.pm.df.index)
        self.pm.add_time_filter(self.time_filter)
        
    @classmethod
    def tearDown(self):
        pass
        
    def test_check_timestamp(self):
        #Missing timestamp at 5:00
        #Duplicate timestamp 17:00
        #Non-monotonic timestamp 19:30
        expected = pd.DataFrame(
            [('', pd.Timestamp('2015-01-01 19:30:00'), pd.Timestamp('2015-01-01 19:30:00'), 1.0, 'Nonmonotonic timestamp'),
             ('', pd.Timestamp('2015-01-01 17:00:00'), pd.Timestamp('2015-01-01 17:00:00'), 1.0, 'Duplicate timestamp'),
             ('', pd.Timestamp('2015-01-01 05:00:00'), pd.Timestamp('2015-01-01 05:00:00'), 1.0, 'Missing timestamp')],
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'])
        
        # Object-oriented test
        test_results = self.pm.test_results
        assert_frame_equal(test_results, expected, check_dtype=False)
        
        # Functional test
        results = pecos.monitoring.check_timestamp(self.raw_data, 900)
        test_results = results['test_results']
        assert_frame_equal(test_results, expected, check_dtype=False)

    def test_check_missing(self):
        #Column D is missing data from 17:45 until 18:15
        expected = pd.DataFrame(
            [('D', pd.Timestamp('2015-01-01 17:45:00'), pd.Timestamp('2015-01-01 18:15:00'), 3.0, 'Missing data')],
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'])
        
        # Object-oriented test
        self.pm.check_missing()
        test_results = self.pm.test_results[self.pm.test_results['Error Flag'] == 'Missing data']
        assert_frame_equal(test_results.reset_index(drop=True), expected, check_dtype=False)
        
        # Functional test
        results = pecos.monitoring.check_missing(self.raw_data)
        test_results = results['test_results']
        assert_frame_equal(test_results, expected, check_dtype=False)
        
    def test_check_corrupt(self):
        #Column C has corrupt data (-999) between 7:30 and 9:30
        expected = pd.DataFrame(
            [('C', pd.Timestamp('2015-01-01 07:30:00'), pd.Timestamp('2015-01-01 09:30:00'), 9.0, 'Corrupt data')],
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'])
        
        # Object-oriented test
        self.pm.check_corrupt([-999])
        test_results = self.pm.test_results[self.pm.test_results['Error Flag'] == 'Corrupt data']
        assert_frame_equal(test_results.reset_index(drop=True), expected, check_dtype=False)
        
        # Functional test
        results = pecos.monitoring.check_corrupt(self.raw_data, [-999])
        test_results = results['test_results']
        assert_frame_equal(test_results, expected, check_dtype=False)

    def test_check_range(self):
        #Column B is below the expected lower bound of 0 at 6:30 and above the expected upper bound of 1 at 15:30
        #Column D is occasionally below the expected lower bound of -1 around midday (2 time steps) and above the expected upper bound of 1 in the early morning and late evening (10 time steps).
        expected = pd.DataFrame(
            [('B', pd.Timestamp('2015-01-01 06:30:00'), pd.Timestamp('2015-01-01 06:30:00'), 1.0, 'Data < lower bound, 0'),
             ('B', pd.Timestamp('2015-01-01 15:30:00'), pd.Timestamp('2015-01-01 15:30:00'), 1.0, 'Data > upper bound, 1'),
             ('D', pd.Timestamp('2015-01-01 11:15:00'), pd.Timestamp('2015-01-01 11:15:00'), 1.0, 'Data < lower bound, -1'),
             ('D', pd.Timestamp('2015-01-01 12:45:00'), pd.Timestamp('2015-01-01 12:45:00'), 1.0, 'Data < lower bound, -1'),
             ('D', pd.Timestamp('2015-01-01 03:15:00'), pd.Timestamp('2015-01-01 03:30:00'), 2.0, 'Data > upper bound, 1'),
             ('D', pd.Timestamp('2015-01-01 04:00:00'), pd.Timestamp('2015-01-01 04:00:00'), 1.0, 'Data > upper bound, 1'),
             ('D', pd.Timestamp('2015-01-01 04:30:00'), pd.Timestamp('2015-01-01 04:45:00'), 2.0, 'Data > upper bound, 1'),
             ('D', pd.Timestamp('2015-01-01 18:30:00'), pd.Timestamp('2015-01-01 18:45:00'), 2.0, 'Data > upper bound, 1'),
             ('D', pd.Timestamp('2015-01-01 19:15:00'), pd.Timestamp('2015-01-01 19:45:00'), 3.0, 'Data > upper bound, 1')],
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'])

        # Object-oriented test
        self.pm.check_corrupt([-999])
        self.pm.check_range([0, 1], 'Random')
        self.pm.check_range([-1, 1], 'Wave')
        test_results = self.pm.test_results[['Data' in ef for ef in self.pm.test_results['Error Flag']]]
        assert_frame_equal(test_results.reset_index(drop=True), expected, check_dtype=False)
        
        # Functional tests
        results = pecos.monitoring.check_timestamp(self.raw_data, 900)
        results = pecos.monitoring.check_corrupt(results['cleaned_data'], [-999])
        raw_data = results['cleaned_data'].loc[self.time_filter,:]
        
        results = pecos.monitoring.check_range(raw_data[['B']],[0, 1])
        test_results = results['test_results']
        assert_frame_equal(test_results,
                           expected.loc[expected['Variable Name'] == 'B',:].reset_index(drop=True), 
                           check_dtype=False)
        
        results = pecos.monitoring.check_range(raw_data[['C','D']],[-1, 1])
        test_results = results['test_results']
        assert_frame_equal(test_results,
                           expected.loc[expected['Variable Name'] == 'D',:].reset_index(drop=True), 
                           check_dtype=False)
        
    def test_check_increment(self):
        #Column A has the same value (0.5) from 12:00 until 14:30
        #Column C does not follow the expected sine function from 13:00 until 16:15. The change is abrupt and gradually corrected.
        expected = pd.DataFrame(
            [('A', pd.Timestamp('2015-01-01 12:15:00'), pd.Timestamp('2015-01-01 14:30:00'), 10.0, '|Increment| < lower bound, 0.0001'),
             ('C', pd.Timestamp('2015-01-01 13:00:00'), pd.Timestamp('2015-01-01 13:00:00'), 1.0, '|Increment| > upper bound, 0.6')],
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'])
        
        # Object-oriented test
        self.pm.check_corrupt([-999])
        self.pm.check_increment([0.0001, None], 'Linear')
        self.pm.check_increment([0.0001, None], 'Random')
        self.pm.check_increment([0.0001, 0.6], 'Wave')
        test_results = self.pm.test_results[['Increment' in ef for ef in self.pm.test_results['Error Flag']]]
        assert_frame_equal(test_results.reset_index(drop=True), expected, check_dtype=False)
        
        # Functional tests
        results = pecos.monitoring.check_timestamp(self.raw_data, 900)
        results = pecos.monitoring.check_corrupt(results['cleaned_data'], [-999])
        raw_data = results['cleaned_data'].loc[self.time_filter,:]
        
        results = pecos.monitoring.check_increment(raw_data[['A']],[0.0001, None])
        test_results = results['test_results']
        assert_frame_equal(test_results,
                           expected.loc[expected['Variable Name'] == 'A',:].reset_index(drop=True), 
                           check_dtype=False)
    
    def test_check_delta(self):
        #Column A has the same value (0.5) from 12:00 until 14:30
        #Column C does not follow the expected sine function from 13:00 until 16:15. 
        #The change is abrupt and gradually corrected.
        expected = pd.DataFrame(
            [('A', pd.Timestamp('2015-01-01 12:00:00'), pd.Timestamp('2015-01-01 14:30:00'), 11.0, 'Delta < lower bound, 0.0001'),
             ('C', pd.Timestamp('2015-01-01 12:45:00'), pd.Timestamp('2015-01-01 13:00:00'), 2.0,  'Delta > upper bound, 0.6')],
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'])
        
        # Object-oriented test
        self.pm.check_corrupt([-999])
        self.pm.check_delta([0.0001, None], window=2*3600)
        self.pm.check_delta([None, 0.6], 'Wave', window=900)
        test_results = self.pm.test_results[['Delta' in ef for ef in self.pm.test_results['Error Flag']]]
        
        #pecos.graphics.plot_test_results(self.pm.df, self.pm.test_results, filename_root='test_check_delta')
        
        assert_frame_equal(test_results.reset_index(drop=True), expected, check_dtype=False)

        # Functional tests
        results = pecos.monitoring.check_timestamp(self.raw_data, 900)
        results = pecos.monitoring.check_corrupt(results['cleaned_data'], [-999])
        raw_data = results['cleaned_data'].loc[self.time_filter,:]
        
        results = pecos.monitoring.check_delta(raw_data[['A']],[0.0001, None], window=2*3600)
        test_results = results['test_results']

        assert_frame_equal(test_results,
                           expected.loc[expected['Variable Name'] == 'A',:].reset_index(drop=True), 
                           check_dtype=False)

    def test_composite_signal(self):
        self.pm.check_corrupt([-999])
        
        clocktime = pecos.utils.datetime_to_clocktime(self.pm.df.index)
        wave_model = np.array(np.sin(10*clocktime/86400))
        wave_measurments = self.pm.df[self.pm.trans['Wave']]
        wave_abs_error = np.abs(wave_measurments.subtract(wave_model,axis=0))
        wave_abs_error.columns=['Wave Error C', 'Wave Error D']
        self.pm.add_dataframe(wave_abs_error)
        self.pm.add_translation_dictionary({'Wave Error': ['Wave Error C', 'Wave Error D']})

        self.pm.check_range([None, 0.25], 'Wave Error')

        temp = self.pm.test_results[['Data' in ef for ef in self.pm.test_results['Error Flag']]]
        temp.index = np.arange(temp.shape[0])

        expected = pd.DataFrame(
            [('Wave Error C',pd.Timestamp('2015-01-01 13:00:00'),pd.Timestamp('2015-01-01 14:45:00'),8.0,'Data > upper bound, 0.25')],
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'])

        assert_frame_equal(temp, expected, check_dtype=False)

    def test_full_example(self):
        data_file = join(simpleexampledir,'simple.xlsx')
        df = pd.read_excel(data_file, index_col=0)

        QCI = simple_example_run_analysis(df)

        assert_almost_equal(QCI.mean(),0.852113,6)

        actual = pd.read_csv('test_results.csv', index_col=0)
        # Convert back to datetime just so that they are in the same format
        actual['Start Time'] = pd.to_datetime(actual['Start Time'])
        actual['End Time'] = pd.to_datetime(actual['End Time'])
        
        expected = pd.read_csv(join(datadir,'Simple_test_results.csv'), index_col=0)
        # Convert back to datetime just so that they are in the same format
        expected['Start Time'] = pd.to_datetime(expected['Start Time'])
        expected['End Time'] = pd.to_datetime(expected['End Time'])
        
        assert_frame_equal(actual, expected, check_dtype=False)
    
    def test_millisecond_timestamp(self):
        data_file = join(simpleexampledir,'simple.xlsx')
        df = pd.read_excel(data_file, index_col=0)
        
        index = pecos.utils.datetime_to_elapsedtime(df.index)
        df.index = index/1e5 # millisecond resolution
        
        df.index = pecos.utils.index_to_datetime(df.index)
        pm = pecos.monitoring.PerformanceMonitoring()

        # Populate the PerformanceMonitoring instance
        pm.add_dataframe(df)
    
        # Check timestamp
        pm.check_timestamp(900/1e5)
    
        expected = pd.DataFrame(
            [('', pd.Timestamp('1970-01-01 00:00:00.702'), pd.Timestamp('1970-01-01 00:00:00.702'), 1.0, 'Nonmonotonic timestamp'),
             ('', pd.Timestamp('1970-01-01 00:00:00.612'), pd.Timestamp('1970-01-01 00:00:00.612'), 1.0, 'Duplicate timestamp'),
             ('', pd.Timestamp('1970-01-01 00:00:00.180'), pd.Timestamp('1970-01-01 00:00:00.180'), 1.0, 'Missing timestamp')],
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'])
        
        assert_frame_equal(pm.test_results, expected, check_dtype=False)

    def test_full_example_with_timezone(self):
        data_file = join(simpleexampledir,'simple.xlsx')
        df = pd.read_excel(data_file, index_col=0)
        df.index = df.index.tz_localize('MST')

        QCI = simple_example_run_analysis(df)

        assert_almost_equal(QCI.mean(),0.852113,6)

        actual = pd.read_csv('test_results.csv', index_col=0)
        expected = pd.read_csv(join(datadir,'Simple_test_results_with_timezone.csv'), index_col=0)
        assert_frame_equal(actual, expected, check_dtype=False)

class Test_check_timestamp(unittest.TestCase):

    @classmethod
    def setUp(self):
        # one occurance in the first hour, none in the second, and two in
        # the third
        index = pd.DatetimeIndex([pd.Timestamp('20161017 01:05:00'),
                                  pd.Timestamp('20161017 03:03:00'),
                                  pd.Timestamp('20161017 03:50:00')])
        df = pd.DataFrame({'A': [0, 2, 3], 'B': [4, np.nan, 6]}, index=index)

        self.pm = pecos.monitoring.PerformanceMonitoring()
        self.pm.add_dataframe(df)

    @classmethod
    def tearDown(self):
        pass

    def test_check_exact_times_true(self):
        self.pm.check_timestamp(3600, exact_times=True)
        expected = pd.DataFrame(
            array([['', Timestamp('2016-10-17 02:05:00'),
                   Timestamp('2016-10-17 03:05:00'), 2,
                   'Missing timestamp']], dtype=object),
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'],
            index=RangeIndex(start=0, stop=1, step=1)
            )
        assert_frame_equal(expected, self.pm.test_results)

    def test_check_exact_times_false(self):
        self.pm.check_timestamp(3600, exact_times=False)
        expected = pd.DataFrame(
            array([['', Timestamp('2016-10-17 02:00:00'),
                    Timestamp('2016-10-17 02:00:00'), 1, 'Missing timestamp']], dtype=object),
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'],
            index=RangeIndex(start=0, stop=1, step=1)
            )
        assert_frame_equal(expected, self.pm.test_results)

    def test_check_exact_times_true_with_start_time(self):
        self.pm.check_timestamp(3600, expected_start_time=Timestamp('2016-10-17 01:00:00'), exact_times=True)
        expected = pd.DataFrame(
            array([['', Timestamp('2016-10-17 01:00:00'),
                   Timestamp('2016-10-17 03:00:00'), 3,
                   'Missing timestamp']], dtype=object),
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'],
            index=RangeIndex(start=0, stop=1, step=1)
            )
        assert_frame_equal(expected, self.pm.test_results)

class Test_check_delta(unittest.TestCase):

    @classmethod
    def setUp(self):
        index = pd.date_range('1/1/2017', periods=24, freq='H')
        data = {'A': [0.5,-0.3,0.2,0,0.5,-0.45,0.35,-0.4,0.5,1.5,0.5,-0.5,0.5,-0.5,5,6,10,10.5,10,10.3,10,10.8,10,9.9], 
                'B': [0,1,2.2,3,3.8,5,6,7.1,8,9,10,5,-2,1,0,0.5,0,5,3,9.5,8.2,7,np.nan,5]}
        df = pd.DataFrame(data, index=index)
        trans = dict(zip(df.columns, [[col] for col in df.columns]))
        
        self.pm = pecos.monitoring.PerformanceMonitoring()
        self.pm.add_dataframe(df)
        self.pm.add_translation_dictionary(trans)

    @classmethod
    def tearDown(self):
        pass
    
    def test_deadsensor(self):
        # dead sensor = < 1 in 5 hours
        self.pm.check_delta([1, None], window=5*3600)
        expected = pd.DataFrame(
            array([['A', Timestamp('2017-01-01 01:00:00'), Timestamp('2017-01-01 08:00:00'), 8, 'Delta < lower bound, 1'],
                   ['A', Timestamp('2017-01-01 16:00:00'), Timestamp('2017-01-01 23:00:00'), 8, 'Delta < lower bound, 1']], dtype=object),
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'],
            index=RangeIndex(start=0, stop=2, step=1)
            )
        #pecos.graphics.plot_test_results(self.pm.df, self.pm.test_results, filename_root='test_deadsensor')
        assert_frame_equal(expected, self.pm.test_results)
        
    def test_abrupt_change(self):
        # abrupt change = > 7 in 3 hours
        self.pm.check_delta([None, 7], window=3*3600)
        expected = pd.DataFrame(
            array([['A', Timestamp('2017-01-01 13:00:00'), Timestamp('2017-01-01 16:00:00'), 4, 'Delta > upper bound, 7'],
                   ['B', Timestamp('2017-01-01 10:00:00'), Timestamp('2017-01-01 12:00:00'), 3, 'Delta > upper bound, 7'],
                   ['B', Timestamp('2017-01-01 16:00:00'), Timestamp('2017-01-01 19:00:00'), 4, 'Delta > upper bound, 7']], dtype=object),
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'],
            index=RangeIndex(start=0, stop=3, step=1)
            )
        assert_frame_equal(expected, self.pm.test_results)

    def test_abrupt_positive_change(self):
        # abrupt positive change = > 7 in 3 hours
        self.pm.check_delta([None, 7], window=3*3600, direction='positive')
        expected = pd.DataFrame(
            array([['A', Timestamp('2017-01-01 13:00:00'), Timestamp('2017-01-01 16:00:00'), 4, 'Delta (+) > upper bound, 7'],
                   ['B', Timestamp('2017-01-01 16:00:00'), Timestamp('2017-01-01 19:00:00'), 4, 'Delta (+) > upper bound, 7']], dtype=object),
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'],
            index=RangeIndex(start=0, stop=2, step=1)
            )
        assert_frame_equal(expected, self.pm.test_results)
        
    def test_abrupt_negative_change(self):
        # abrupt negative change = < 7 in 3 hours
        self.pm.check_delta([None, 7], window=3*3600, direction='negative')
        expected = pd.DataFrame(
            array([['B', Timestamp('2017-01-01 10:00:00'), Timestamp('2017-01-01 12:00:00'), 3, 'Delta (-) > upper bound, 7']], dtype=object),
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'],
            index=RangeIndex(start=0, stop=1, step=1)
            )
        assert_frame_equal(expected, self.pm.test_results)

    def test_delta_scale(self, generate_output=False):
        # The following function was used to test scalability of the delta test
        # by increasing N and timing results.  The data includes stagnant data and 
        # abrupt changes (some positive some negative) of varing degree.  This 
        # function could be built into a formal test by adding assert statements
        import time
        
        np.random.seed(123)
    
        N = 100 # number of data points per column
        ndays = 7
        
        t = np.arange(0,2*np.pi,2*np.pi/N)
        t = t[0:N]
        sinwaveA = 10*np.sin(ndays*t)
        sinwaveB = 5*np.sin(ndays*t)
        sinwaveC = 1*np.sin(ndays*t)
        noiseA = np.array(np.random.normal(0,1,N))
        noiseB = np.array(np.random.normal(0,0.5,N))
        noiseC = np.array(np.random.normal(0,0.1,N))
        t = t*(24*ndays)/(2*np.pi)
        
        df = pd.DataFrame(columns=['A', 'B'], index=t)
        df.index = pecos.utils.index_to_datetime(df.index, unit='h')
        
        # Sin wave with noise
        df['A'] = sinwaveA+noiseA # delta = 20
        df['B'] = sinwaveB+noiseB # delta = 10
        df['C'] = sinwaveC+noiseC # delta = 2
        
        # Random, truncated normal distribution, delta = 5
        num = df.loc['1970-01-03',:].shape[0]
        normdist = np.random.normal(0,1,num) 
        normdist[normdist > 2.5] = 2.5
        normdist[normdist < -2.5] = -2.5
        df.loc['1970-01-03','A'] = normdist
        df.loc['1970-01-03','B'] = normdist
        df.loc['1970-01-03','C'] = normdist
        
        # Uniform, value of 1, delta = 0
        df.loc['1970-01-05',:] = 1 
        
        # Steep decline (delta = 20,10,2), followed by delta = 1
        num = df.loc['1970-01-06 06:00:00':'1970-01-06 18:00:00',:].shape[0]
        noise = np.array(np.random.rand(num))-0.5
        df.loc['1970-01-06 06:00:00':'1970-01-06 18:00:00','A'] = -10+noise 
        df.loc['1970-01-06 06:00:00':'1970-01-06 18:00:00','B'] = -5+noise
        df.loc['1970-01-06 06:00:00':'1970-01-06 18:00:00','C'] = -1+noise
        
        if generate_output:
            df.plot()
        
        for lb in [2,5,10,20]:
            for direction in ['both', 'positive', 'negative']:
                tic = time.time()
                results = pecos.monitoring.check_delta(df, [lb,None], window=12*3600, direction=direction)
                if generate_output:
                    print('lb', lb, direction, time.time() - tic, sum(results['test_results']['Timesteps']))
                    pecos.graphics.plot_test_results(df, results['test_results'], filename_root='lb'+str(lb)+'_'+direction)
        
        for ub in [2,5,10,20]:
            for direction in ['both', 'positive', 'negative']:
                tic = time.time()
                results = pecos.monitoring.check_delta(df, [None,ub], window=12*3600, direction=direction)
                if generate_output:
                    print('ub', ub, direction, time.time() - tic, sum(results['test_results']['Timesteps']))
                    pecos.graphics.plot_test_results(df, results['test_results'], filename_root='ub'+str(ub)+'_'+direction)
            
        
class Test_check_outlier(unittest.TestCase):

    @classmethod
    def setUp(self):
        index = pd.date_range('1/1/2017', periods=24, freq='H')
        data = {'A': [112,114,113,132,134,127,150,120,117,112,107,99,140,
                      98,88,98,106,110,107,79,102,115,np.nan,91]}
        df = pd.DataFrame(data, index=index)
        trans = dict(zip(df.columns, [[col] for col in df.columns]))
        
        self.pm = pecos.monitoring.PerformanceMonitoring()
        self.pm.add_dataframe(df)
        self.pm.add_translation_dictionary(trans)
        
    @classmethod
    def tearDown(self):
        pass
    
    def test_outlier(self):
        # outlier if stdev > 1.9
        self.pm.check_outlier([-1.9, 1.9], window=None, absolute_value=False)
        expected = pd.DataFrame(
            array([['A', Timestamp('2017-01-01 19:00:00'), Timestamp('2017-01-01 19:00:00'), 1, 'Outlier < lower bound, -1.9'],
                   ['A', Timestamp('2017-01-01 06:00:00'), Timestamp('2017-01-01 06:00:00'), 1, 'Outlier > upper bound, 1.9']], dtype=object),
            columns=['Variable Name', 'Start Time', 'End Time', 'Timesteps', 'Error Flag'],
            index=RangeIndex(start=0, stop=2, step=1)
            )
        assert_frame_equal(expected, self.pm.test_results)

if __name__ == '__main__':
    unittest.main()
