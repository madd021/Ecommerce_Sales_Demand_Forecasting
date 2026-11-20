"""
Comprehensive Statistical Analysis and Demand Forecasting Pipeline
Course: 26MCAC103 / 25MCAC103 - Business Statistics Using Python
Dataset: Kaggle Store Sales - Time Series Forecasting (Corporación Favorita, Ecuador)
"""

import os
import json
import numpy as np
import pandas as pd
import scipy.stats as stats
import matplotlib.pyplot as plt
import seaborn as sns

import statsmodels.api as sm
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.stats.stattools import durbin_watson
from statsmodels.stats.diagnostic import het_breuschpagan, acorr_ljungbox
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Styling
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 10
plt.rcParams['axes.titlesize'] = 12
plt.rcParams['axes.titleweight'] = 'bold'
plt.rcParams['axes.labelsize'] = 10
plt.rcParams['figure.titlesize'] = 14

DATA_DIR = r'd:\BS Project\data'
RESULTS_DIR = r'd:\BS Project\results'
os.makedirs(RESULTS_DIR, exist_ok=True)

def main():
    print("="*70)
    print("STEP 1: LOADING AND PREPROCESSING DATASETS")
    print("="*70)
    
    # 1. Load data
    train = pd.read_csv(os.path.join(DATA_DIR, 'train.csv'), parse_dates=['date'])
    stores = pd.read_csv(os.path.join(DATA_DIR, 'stores.csv'))
    oil = pd.read_csv(os.path.join(DATA_DIR, 'oil.csv'), parse_dates=['date'])
    holidays = pd.read_csv(os.path.join(DATA_DIR, 'holidays_events.csv'), parse_dates=['date'])
    transactions = pd.read_csv(os.path.join(DATA_DIR, 'transactions.csv'), parse_dates=['date'])
    
    total_raw_rows = len(train)
    date_min = str(train['date'].min().date())
    date_max = str(train['date'].max().date())
    num_stores = train['store_nbr'].nunique()
    num_families = train['family'].nunique()
    
    print(f"Train rows: {total_raw_rows:,}")
    print(f"Date range: {date_min} to {date_max}")
    print(f"Stores: {num_stores}, Families: {num_families}")
    
    # 2. Build Daily Aggregated Series
    daily = train.groupby('date').agg({'sales': 'sum', 'onpromotion': 'sum'}).reset_index()
    
    # Reindex for continuous daily calendar
    full_dates = pd.date_range(start=train['date'].min(), end=train['date'].max(), freq='D')
    missing_dates = full_dates.difference(daily['date'])
    print(f"Missing calendar dates (e.g. Christmas closures): {[d.strftime('%Y-%m-%d') for d in missing_dates]}")
    
    daily = daily.set_index('date').reindex(full_dates, fill_value=0).reset_index()
    daily.rename(columns={'index': 'date'}, inplace=True)
    daily['date'] = pd.to_datetime(daily['date'])
    
    # Merge oil
    daily = pd.merge(daily, oil, on='date', how='left')
    daily['dcoilwtico'] = daily['dcoilwtico'].interpolate(method='linear').bfill().ffill()
    
    # Merge holidays
    valid_holidays = holidays[holidays['transferred'] == False]
    holiday_set = set(valid_holidays['date'].dt.date)
    daily['is_holiday'] = daily['date'].dt.date.isin(holiday_set).astype(int)
    
    # Calendar features
    daily['day_name'] = daily['date'].dt.day_name()
    daily['dayofweek'] = daily['date'].dt.dayofweek
    daily['is_weekend'] = daily['dayofweek'].isin([5, 6]).astype(int)
    daily['month'] = daily['date'].dt.month
    daily['month_name'] = daily['date'].dt.month_name()
    daily['year'] = daily['date'].dt.year
    daily['time_idx'] = np.arange(len(daily))
    
    print(f"Daily aggregated records: {len(daily)}")
    
    print("\n" + "="*70)
    print("STEP 2: DESCRIPTIVE STATISTICS")
    print("="*70)
    
    sales_series = daily['sales']
    mean_val = float(sales_series.mean())
    median_val = float(sales_series.median())
    std_val = float(sales_series.std())
    var_val = float(sales_series.var())
    min_val = float(sales_series.min())
    max_val = float(sales_series.max())
    range_val = float(max_val - min_val)
    q1_val = float(sales_series.quantile(0.25))
    q3_val = float(sales_series.quantile(0.75))
    iqr_val = float(q3_val - q1_val)
    cv_val = float((std_val / mean_val) * 100) # Coefficient of variation %
    skew_val = float(sales_series.skew())
    kurt_val = float(sales_series.kurtosis())
    
    # Outlier count via 1.5*IQR
    lower_bound = q1_val - 1.5 * iqr_val
    upper_bound = q3_val + 1.5 * iqr_val
    outliers_count = int(((sales_series < lower_bound) | (sales_series > upper_bound)).sum())
    
    desc_stats = {
        'count': int(len(sales_series)),
        'mean': mean_val,
        'median': median_val,
        'std': std_val,
        'variance': var_val,
        'min': min_val,
        'max': max_val,
        'range': range_val,
        'q1': q1_val,
        'q3': q3_val,
        'iqr': iqr_val,
        'cv_percent': cv_val,
        'skewness': skew_val,
        'kurtosis': kurt_val,
        'outlier_count': outliers_count,
        'iqr_lower_bound': lower_bound,
        'iqr_upper_bound': upper_bound
    }
    
    df_desc = pd.DataFrame([desc_stats]).T
    df_desc.columns = ['Value']
    df_desc.to_csv(os.path.join(RESULTS_DIR, 'descriptive_stats.csv'))
    print("Daily Sales Descriptive Statistics:\n", df_desc)
    
    # Correlation analysis
    corr_vars = ['sales', 'onpromotion', 'dcoilwtico', 'is_holiday', 'is_weekend']
    corr_matrix = daily[corr_vars].corr()
    corr_matrix.to_csv(os.path.join(RESULTS_DIR, 'correlation_matrix.csv'))
    print("\nCorrelation Matrix:\n", corr_matrix)
    
    # Family sales breakdown
    family_sales = train.groupby('family')['sales'].agg(['sum', 'mean']).sort_values('sum', ascending=False)
    family_sales['cumulative_sum'] = family_sales['sum'].cumsum()
    family_sales['cumulative_pct'] = (family_sales['cumulative_sum'] / family_sales['sum'].sum()) * 100
    family_sales.head(15).to_csv(os.path.join(RESULTS_DIR, 'top_families_sales.csv'))
    
    # Store sales breakdown
    store_sales = train.groupby('store_nbr')['sales'].sum().reset_index()
    store_merged = pd.merge(store_sales, stores, on='store_nbr').sort_values('sales', ascending=False)
    store_merged.to_csv(os.path.join(RESULTS_DIR, 'store_sales_summary.csv'), index=False)
    
    print("\n" + "="*70)
    print("STEP 3: INFERENTIAL STATISTICS (HYPOTHESIS TESTING)")
    print("="*70)
    
    weekday_sales = daily[daily['is_weekend'] == 0]['sales']
    weekend_sales = daily[daily['is_weekend'] == 1]['sales']
    
    t_stat, p_val = stats.ttest_ind(weekend_sales, weekday_sales, equal_var=False)
    mean_diff = float(weekend_sales.mean() - weekday_sales.mean())
    n_we = len(weekend_sales)
    n_wd = len(weekday_sales)
    s_we = weekend_sales.std()
    s_wd = weekday_sales.std()
    
    se_diff = float(np.sqrt((s_we**2 / n_we) + (s_wd**2 / n_wd)))
    df_welch = float(((s_we**2 / n_we) + (s_wd**2 / n_wd))**2 / 
                     (((s_we**2 / n_we)**2 / (n_we - 1)) + ((s_wd**2 / n_wd)**2 / (n_wd - 1))))
    
    crit_val = stats.t.ppf(0.975, df_welch)
    ci_lower = mean_diff - crit_val * se_diff
    ci_upper = mean_diff + crit_val * se_diff
    cohen_d = float(mean_diff / np.sqrt(((n_we - 1)*s_we**2 + (n_wd - 1)*s_wd**2) / (n_we + n_wd - 2)))
    
    # Store Type One-Way ANOVA
    train_store = pd.merge(train.groupby(['date', 'store_nbr'])['sales'].sum().reset_index(), stores, on='store_nbr')
    store_types = [group['sales'].values for _, group in train_store.groupby('type')]
    f_stat, anova_p = stats.f_oneway(*store_types)
    
    # Serial correlation check (Ljung-Box & Durbin-Watson)
    lb_test = acorr_ljungbox(sales_series, lags=[1, 7, 14], return_df=True)
    lag1_autocorr = float(sales_series.autocorr(lag=1))
    lag7_autocorr = float(sales_series.autocorr(lag=7))
    
    inferential_results = {
        'weekday_count': n_wd,
        'weekday_mean': float(weekday_sales.mean()),
        'weekday_std': float(s_wd),
        'weekend_count': n_we,
        'weekend_mean': float(weekend_sales.mean()),
        'weekend_std': float(s_we),
        'mean_difference': mean_diff,
        'std_error_diff': se_diff,
        'welch_t_stat': float(t_stat),
        'p_value': float(p_val),
        'degrees_of_freedom': df_welch,
        'ci_95_lower': float(ci_lower),
        'ci_95_upper': float(ci_upper),
        'cohen_d': cohen_d,
        'anova_f_stat': float(f_stat),
        'anova_p_val': float(anova_p),
        'lag1_autocorr': lag1_autocorr,
        'lag7_autocorr': lag7_autocorr,
        'ljung_box_p_lag7': float(lb_test.loc[7, 'lb_pvalue'])
    }
    
    print(f"Welch t-stat: {t_stat:.4f}, p-value: {p_val:.4e}")
    print(f"Mean Difference: ${mean_diff:,.2f} [95% CI: ${ci_lower:,.2f} to ${ci_upper:,.2f}]")
    print(f"Store Type ANOVA F-stat: {f_stat:.2f}, p-value: {anova_p:.4e}")
    print(f"Lag-1 Autocorr: {lag1_autocorr:.4f}, Lag-7 Autocorr: {lag7_autocorr:.4f}")
    
    print("\n" + "="*70)
    print("STEP 4: REGRESSION ANALYSIS")
    print("="*70)
    
    # Create regression dataset
    df_reg = pd.get_dummies(daily, columns=['day_name', 'month'], drop_first=True, dtype=float)
    
    # Chronological Split: Last 31 days (2017-07-16 to 2017-08-15) as Holdout
    test_days = 31
    train_mask = df_reg['date'] < df_reg['date'].iloc[-test_days]
    
    # Exclude redundant variables to guarantee full rank (is_weekend is collinear with Saturday/Sunday dummies)
    feature_cols = [c for c in df_reg.columns if c not in ['date', 'sales', 'month_name', 'year', 'dayofweek', 'is_weekend']]
    
    X_train = sm.add_constant(df_reg.loc[train_mask, feature_cols])
    y_train = df_reg.loc[train_mask, 'sales']
    
    X_test = sm.add_constant(df_reg.loc[~train_mask, feature_cols])
    y_test = df_reg.loc[~train_mask, 'sales']
    
    ols_model = sm.OLS(y_train, X_train).fit()
    y_pred_reg_test = ols_model.predict(X_test)
    y_pred_reg_train = ols_model.predict(X_train)
    
    reg_train_r2 = float(ols_model.rsquared)
    reg_train_adj_r2 = float(ols_model.rsquared_adj)
    reg_test_r2 = float(r2_score(y_test, y_pred_reg_test))
    reg_test_mae = float(mean_absolute_error(y_test, y_pred_reg_test))
    reg_test_rmse = float(np.sqrt(mean_squared_error(y_test, y_pred_reg_test)))
    reg_test_mape = float(np.mean(np.abs((y_test - y_pred_reg_test) / y_test)) * 100)
    
    # Residual diagnostics
    train_residuals = ols_model.resid
    dw_stat = float(durbin_watson(train_residuals))
    jb_stat, jb_p = stats.jarque_bera(train_residuals)
    bp_stat, bp_p, _, _ = het_breuschpagan(train_residuals, X_train)
    
    # Save coefficients
    coeff_df = pd.DataFrame({
        'Coefficient': ols_model.params,
        'Std_Error': ols_model.bse,
        't_statistic': ols_model.tvalues,
        'p_value': ols_model.pvalues
    })
    coeff_df.to_csv(os.path.join(RESULTS_DIR, 'regression_coefficients.csv'))
    
    reg_results = {
        'train_r2': reg_train_r2,
        'train_adj_r2': reg_train_adj_r2,
        'test_r2': reg_test_r2,
        'test_mae': reg_test_mae,
        'test_rmse': reg_test_rmse,
        'test_mape': reg_test_mape,
        'f_statistic': float(ols_model.fvalue),
        'f_pvalue': float(ols_model.f_pvalue),
        'durbin_watson': dw_stat,
        'jarque_bera_stat': float(jb_stat),
        'jarque_bera_p': float(jb_p),
        'breusch_pagan_p': float(bp_p),
        'key_coeffs': {
            'time_idx': float(ols_model.params.get('time_idx', 0)),
            'onpromotion': float(ols_model.params.get('onpromotion', 0)),
            'is_holiday': float(ols_model.params.get('is_holiday', 0)),
            'dcoilwtico': float(ols_model.params.get('dcoilwtico', 0))
        }
    }
    
    print(f"Regression Train R2: {reg_train_r2:.4f}, Test R2: {reg_test_r2:.4f}")
    print(f"Test MAE: {reg_test_mae:,.2f}, Test RMSE: {reg_test_rmse:,.2f}")
    print(f"Durbin-Watson: {dw_stat:.4f}, Breusch-Pagan p-val: {bp_p:.4e}")
    
    print("\n" + "="*70)
    print("STEP 5: TIME-SERIES DEMAND FORECASTING (5 MODELS)")
    print("="*70)
    
    # Series with continuous daily index
    ts_train = daily.loc[train_mask].set_index('date')['sales'].asfreq('D')
    ts_test = daily.loc[~train_mask].set_index('date')['sales'].asfreq('D')
    test_index = ts_test.index
    
    # Model 1: Naive (Persistence / Lag 1)
    naive_preds = pd.Series([ts_train.iloc[-1]] + list(ts_test.iloc[:-1]), index=test_index)
    
    # Model 2: Seasonal Naive (Lag 7)
    snaive_preds = pd.Series([ts_train.iloc[-7 + (i % 7)] for i in range(len(ts_test))], index=test_index)
    
    # Model 3: 7-Day Rolling Moving Average
    hist_vals = list(ts_train.values)
    ma7_preds = []
    for i in range(len(ts_test)):
        ma7_preds.append(np.mean(hist_vals[-7:]))
        hist_vals.append(ts_test.iloc[i])
    ma7_preds = pd.Series(ma7_preds, index=test_index)
    
    # Model 4: Multiple Linear Regression (from Step 4)
    reg_preds = pd.Series(y_pred_reg_test.values, index=test_index)
    
    # Model 5: Holt-Winters Exponential Smoothing (Additive Trend, Additive 7-Day Seasonality)
    hw_fit = ExponentialSmoothing(ts_train, trend='add', seasonal='add', seasonal_periods=7).fit()
    hw_preds = hw_fit.forecast(test_days)
    
    # Model 6: SARIMA(1, 1, 1) x (1, 1, 1, 7)
    sarima_fit = SARIMAX(
        ts_train, 
        order=(1, 1, 1), 
        seasonal_order=(1, 1, 1, 7), 
        enforce_stationarity=False, 
        enforce_invertibility=False
    ).fit(disp=False)
    sarima_preds = sarima_fit.forecast(test_days)
    
    # Comparison Table
    forecast_models = {
        'Naive (Persistence)': naive_preds,
        '7-Day Rolling Moving Average': ma7_preds,
        'Seasonal Naive (Lag-7)': snaive_preds,
        'Multiple Linear Regression': reg_preds,
        'Holt-Winters Exp Smoothing': hw_preds,
        'SARIMA(1,1,1)x(1,1,1,7)': sarima_preds
    }
    
    forecast_eval = []
    for name, p_series in forecast_models.items():
        m_mae = float(mean_absolute_error(ts_test, p_series))
        m_rmse = float(np.sqrt(mean_squared_error(ts_test, p_series)))
        m_mape = float(np.mean(np.abs((ts_test - p_series) / ts_test)) * 100)
        m_r2 = float(r2_score(ts_test, p_series))
        forecast_eval.append({
            'Model': name,
            'MAE': m_mae,
            'RMSE': m_rmse,
            'MAPE (%)': m_mape,
            'R2': m_r2
        })
    
    df_forecast_eval = pd.DataFrame(forecast_eval).sort_values('RMSE')
    df_forecast_eval.to_csv(os.path.join(RESULTS_DIR, 'forecast_comparison.csv'), index=False)
    print("\nForecast Performance on Unseen 31-Day Holdout:\n", df_forecast_eval.to_string(index=False))
    
    # Future 16-Day Forecast (2017-08-16 to 2017-08-31)
    full_daily_series = daily.set_index('date')['sales'].asfreq('D')
    best_hw_full = ExponentialSmoothing(full_daily_series, trend='add', seasonal='add', seasonal_periods=7).fit()
    future_hw_16 = best_hw_full.forecast(16)
    
    best_sarima_full = SARIMAX(
        full_daily_series, 
        order=(1, 1, 1), 
        seasonal_order=(1, 1, 1, 7),
        enforce_stationarity=False,
        enforce_invertibility=False
    ).fit(disp=False)
    future_sarima_16 = best_sarima_full.forecast(16)
    future_sarima_res = best_sarima_full.get_forecast(16)
    future_ci = future_sarima_res.conf_int(alpha=0.05)
    
    future_dates = pd.date_range(start='2017-08-16', periods=16, freq='D')
    df_future = pd.DataFrame({
        'date': future_dates,
        'sarima_forecast': future_sarima_16.values,
        'ci_lower_95': future_ci.iloc[:, 0].values,
        'ci_upper_95': future_ci.iloc[:, 1].values,
        'holt_winters_forecast': future_hw_16.values
    })
    df_future.to_csv(os.path.join(RESULTS_DIR, 'future_forecast_16days.csv'), index=False)
    print("\nFuture 16-Day Forecast (Sample):\n", df_future.head())
    
    print("\n" + "="*70)
    print("STEP 6: GENERATING PUBLICATION-READY VISUALISATIONS")
    print("="*70)
    
    # Colors
    c_primary = '#1f77b4'
    c_secondary = '#ff7f0e'
    c_dark = '#2c3e50'
    c_light = '#ecf0f1'
    c_accent = '#27ae60'
    c_danger = '#e74c3c'
    
    # FIG 1: Daily Total Sales Trend & 30-Day Moving Average
    fig, ax = plt.subplots(figsize=(12, 5), dpi=300)
    ax.plot(daily['date'], daily['sales'] / 1e3, label='Daily Network Sales', color='#7f8c8d', alpha=0.45, lw=1)
    ax.plot(daily['date'], daily['sales'].rolling(30).mean() / 1e3, label='30-Day Moving Average (Trend)', color='#2980b9', lw=2.5)
    ax.set_title('Figure 1: Daily Total Sales Trend with 30-Day Moving Average (2013–2017)', pad=12)
    ax.set_xlabel('Date')
    ax.set_ylabel('Total Sales (in Thousands USD)')
    ax.legend(loc='upper left', frameon=True)
    plt.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, 'fig01_daily_sales_trend.png'))
    plt.close()
    
    # FIG 2: Monthly and Weekday Seasonality Heatmap / Patterns
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), dpi=300)
    
    # Weekday barplot
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    weekday_agg = daily.groupby('day_name')['sales'].agg(['mean', 'std']).reindex(day_order)
    axes[0].bar(weekday_agg.index, weekday_agg['mean'] / 1e3, yerr=weekday_agg['std']/1e3, capsize=4, 
                color=['#3498db' if d not in ['Saturday', 'Sunday'] else '#e67e22' for d in day_order], alpha=0.85)
    axes[0].set_title('Mean Daily Sales by Day of Week (with ±1 SD)', pad=10)
    axes[0].set_xlabel('Day of the Week')
    axes[0].set_ylabel('Mean Sales (in Thousands USD)')
    axes[0].tick_params(axis='x', rotation=30)
    
    # Monthly pattern
    month_agg = daily.groupby('month')['sales'].mean()
    axes[1].plot(month_agg.index, month_agg.values / 1e3, marker='o', color='#27ae60', lw=2.5, markersize=7)
    axes[1].fill_between(month_agg.index, month_agg.values / 1e3, alpha=0.15, color='#27ae60')
    axes[1].set_title('Mean Daily Sales by Month (Annual Seasonality)', pad=10)
    axes[1].set_xlabel('Month of Year')
    axes[1].set_ylabel('Mean Daily Sales (in Thousands USD)')
    axes[1].set_xticks(range(1, 13))
    axes[1].set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
    
    plt.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, 'fig02_monthly_weekday_patterns.png'))
    plt.close()
    
    # FIG 3: Sales Distribution Histogram & Boxplot
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), dpi=300)
    
    # Histogram + KDE
    sns.histplot(daily['sales'] / 1e3, kde=True, ax=axes[0], color='#2980b9', bins=35)
    axes[0].axvline(mean_val / 1e3, color='#e74c3c', linestyle='--', lw=2, label=f'Mean (${mean_val/1e3:,.1f}k)')
    axes[0].axvline(median_val / 1e3, color='#27ae60', linestyle='-', lw=2, label=f'Median (${median_val/1e3:,.1f}k)')
    axes[0].set_title('Figure 3A: Daily Sales Distribution & Skewness', pad=10)
    axes[0].set_xlabel('Total Daily Sales (in Thousands USD)')
    axes[0].set_ylabel('Frequency')
    axes[0].legend(frameon=True)
    
    # Boxplot by Year
    sns.boxplot(x='year', y=daily['sales'] / 1e3, data=daily, ax=axes[1], color='#3498db')
    axes[1].set_title('Figure 3B: Annual Boxplots Showing Variance & Outliers', pad=10)
    axes[1].set_xlabel('Year')
    axes[1].set_ylabel('Total Daily Sales (in Thousands USD)')
    
    plt.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, 'fig03_sales_distribution_boxplots.png'))
    plt.close()
    
    # FIG 4: Top Product Families (Pareto Analysis)
    fig, ax1 = plt.subplots(figsize=(12, 6), dpi=300)
    top10_fam = family_sales.head(10).copy()
    ax1.bar(top10_fam.index, top10_fam['sum'] / 1e6, color='#34495e', alpha=0.85, width=0.6)
    ax1.set_xlabel('Product Family', fontweight='bold')
    ax1.set_ylabel('Total Sales (Millions USD)', color='#34495e', fontweight='bold')
    ax1.tick_params(axis='x', rotation=40)
    
    ax2 = ax1.twinx()
    ax2.plot(top10_fam.index, top10_fam['cumulative_pct'], color='#e74c3c', marker='D', lw=2.2, markersize=6)
    ax2.axhline(80, color='#e74c3c', linestyle=':', label='80% Pareto Threshold')
    ax2.set_ylabel('Cumulative Sales Share (%)', color='#e74c3c', fontweight='bold')
    ax2.set_ylim(0, 105)
    ax2.legend(loc='lower right', frameon=True)
    plt.title('Figure 4: Pareto Analysis of Top 10 Product Families (93.0% of Total Revenue)', pad=12)
    plt.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, 'fig04_top_product_families_pareto.png'))
    plt.close()
    
    # FIG 5: Store Performance Comparisons (Top Stores & Cluster Heatmap)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=300)
    
    # Top 10 stores
    top10_stores = store_merged.head(10)
    sns.barplot(x=top10_stores['sales'] / 1e6, y=top10_stores['store_nbr'].astype(str), ax=axes[0], color='#2980b9')
    axes[0].set_title('Top 10 Stores by Cumulative Sales', pad=10)
    axes[0].set_xlabel('Total Sales (Millions USD)')
    axes[0].set_ylabel('Store Number')
    
    # Sales by Store Type
    type_agg = train_store.groupby('type')['sales'].mean() / 1e3
    sns.barplot(x=type_agg.index, y=type_agg.values, ax=axes[1], color='#e67e22')
    axes[1].set_title('Mean Daily Store Sales by Store Type (A–E)', pad=10)
    axes[1].set_xlabel('Store Type')
    axes[1].set_ylabel('Mean Daily Store Sales (Thousands USD)')
    
    plt.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, 'fig05_store_cluster_comparisons.png'))
    plt.close()
    
    # FIG 6: Promotions and Oil Price vs Sales
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), dpi=300)
    
    # Sales vs Promotions
    axes[0].scatter(daily['onpromotion'] / 1e3, daily['sales'] / 1e3, alpha=0.35, color='#8e44ad', s=20)
    sns.regplot(x=daily['onpromotion'] / 1e3, y=daily['sales'] / 1e3, ax=axes[0], scatter=False, color='#2c3e50')
    axes[0].set_title('Figure 6A: Sales vs Promotion Items Count (r = 0.575)', pad=10)
    axes[0].set_xlabel('Promotion Items Count (Thousands)')
    axes[0].set_ylabel('Total Sales (Thousands USD)')
    
    # Sales vs Oil Price
    axes[1].scatter(daily['dcoilwtico'], daily['sales'] / 1e3, alpha=0.35, color='#d35400', s=20)
    sns.regplot(x=daily['dcoilwtico'], y=daily['sales'] / 1e3, ax=axes[1], scatter=False, color='#2c3e50')
    axes[1].set_title('Figure 6B: Sales vs Crude Oil Price (WTI) (r = -0.628)', pad=10)
    axes[1].set_xlabel('Crude Oil Price ($/bbl)')
    axes[1].set_ylabel('Total Sales (Thousands USD)')
    
    plt.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, 'fig06_promotions_oil_sales_scatter.png'))
    plt.close()
    
    # FIG 7: Hypothesis Testing - Weekday vs Weekend Sales Distribution
    fig, ax = plt.subplots(figsize=(9, 5), dpi=300)
    sns.kdeplot(weekday_sales / 1e3, ax=ax, label=f'Weekday (Mean: ${weekday_sales.mean()/1e3:,.1f}k, n={n_wd})', color='#2980b9', fill=True, alpha=0.3, lw=2)
    sns.kdeplot(weekend_sales / 1e3, ax=ax, label=f'Weekend (Mean: ${weekend_sales.mean()/1e3:,.1f}k, n={n_we})', color='#e67e22', fill=True, alpha=0.3, lw=2)
    ax.axvline(weekday_sales.mean() / 1e3, color='#2980b9', linestyle='--', lw=2)
    ax.axvline(weekend_sales.mean() / 1e3, color='#e67e22', linestyle='--', lw=2)
    ax.set_title(f'Figure 7: Welch t-Test Comparison: Weekday vs Weekend Sales (t = {t_stat:.2f}, p < 0.001)', pad=12)
    ax.set_xlabel('Daily Sales (in Thousands USD)')
    ax.set_ylabel('Probability Density')
    ax.legend(frameon=True, loc='upper right')
    plt.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, 'fig07_inferential_weekday_vs_weekend.png'))
    plt.close()
    
    # FIG 8: Regression Fit and Residual Diagnostics
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), dpi=300)
    
    # Actual vs Predicted on Holdout
    axes[0].plot(test_index, y_test / 1e3, label='Actual Holdout Sales', color='#2c3e50', lw=2)
    axes[0].plot(test_index, y_pred_reg_test / 1e3, label='OLS Regression Predictions', color='#e74c3c', linestyle='--', lw=2)
    axes[0].set_title(f'Figure 8A: OLS Regression Holdout Fit (R² = {reg_test_r2:.3f}, MAE = ${reg_test_mae/1e3:,.1f}k)', pad=10)
    axes[0].set_xlabel('Holdout Date (2017)')
    axes[0].set_ylabel('Daily Sales (Thousands USD)')
    axes[0].legend(frameon=True)
    axes[0].tick_params(axis='x', rotation=30)
    
    # Residual QQ Plot
    sm.qqplot(train_residuals, line='s', ax=axes[1])
    axes[1].set_title('Figure 8B: Regression Residuals Normal Q-Q Plot', pad=10)
    
    plt.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, 'fig08_regression_actual_vs_predicted_residuals.png'))
    plt.close()
    
    # FIG 9: Forecast Model Comparison on Holdout Test Set
    fig, ax = plt.subplots(figsize=(14, 6), dpi=300)
    ax.plot(test_index, ts_test / 1e3, label='Actual Demand', color='#000000', lw=2.5, marker='o', markersize=4)
    ax.plot(test_index, snaive_preds / 1e3, label=f'Seasonal Naive (RMSE: ${forecast_eval[2]["RMSE"]/1e3:,.1f}k)', color='#95a5a6', linestyle=':', lw=1.8)
    ax.plot(test_index, reg_preds / 1e3, label=f'Linear Regression (RMSE: ${reg_test_rmse/1e3:,.1f}k)', color='#3498db', linestyle='--', lw=1.8)
    ax.plot(test_index, hw_preds / 1e3, label=f'Holt-Winters (RMSE: ${forecast_eval[4]["RMSE"]/1e3:,.1f}k)', color='#e67e22', lw=2)
    ax.plot(test_index, sarima_preds / 1e3, label=f'SARIMA (RMSE: ${forecast_eval[5]["RMSE"]/1e3:,.1f}k)', color='#27ae60', lw=2.2)
    ax.set_title('Figure 9: Forecasting Models Evaluation on 31-Day Unseen Holdout (2017-07-16 to 2017-08-15)', pad=12)
    ax.set_xlabel('Holdout Date')
    ax.set_ylabel('Total Sales (in Thousands USD)')
    ax.legend(frameon=True, loc='upper left')
    plt.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, 'fig09_forecast_model_comparisons.png'))
    plt.close()
    
    # FIG 10: Future Demand Forecast (16 Days Ahead)
    fig, ax = plt.subplots(figsize=(13, 5.5), dpi=300)
    # Plot last 30 days of actual
    last_hist_dates = daily['date'].iloc[-30:]
    last_hist_sales = daily['sales'].iloc[-30:]
    ax.plot(last_hist_dates, last_hist_sales / 1e3, label='Recent Historical Demand', color='#2c3e50', lw=2)
    ax.plot(df_future['date'], df_future['sarima_forecast'] / 1e3, label='SARIMA 16-Day Forecast', color='#27ae60', lw=2.5, marker='s', markersize=5)
    ax.fill_between(df_future['date'], df_future['ci_lower_95'] / 1e3, df_future['ci_upper_95'] / 1e3, color='#27ae60', alpha=0.2, label='95% Prediction Interval')
    ax.plot(df_future['date'], df_future['holt_winters_forecast'] / 1e3, label='Holt-Winters Forecast', color='#e67e22', linestyle='--', lw=2)
    ax.set_title('Figure 10: Out-of-Sample Demand Forecast for Next 16 Days (2017-08-16 to 2017-08-31)', pad=12)
    ax.set_xlabel('Date')
    ax.set_ylabel('Forecasted Daily Sales (Thousands USD)')
    ax.legend(frameon=True, loc='upper left')
    plt.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, 'fig10_future_demand_forecast.png'))
    plt.close()
    
    # Save all combined metrics into JSON for reference across report and presentation
    all_metrics = {
        'metadata': {
            'course': '26MCAC103 - Business Statistics Using Python',
            'project_title': 'E-Commerce Sales Analysis and Demand Forecasting',
            'dataset_source': 'Kaggle Store Sales - Time Series Forecasting (Corporación Favorita, Ecuador)',
            'url': 'https://www.kaggle.com/competitions/store-sales-time-series-forecasting/data',
            'total_rows': total_raw_rows,
            'daily_rows': len(daily),
            'start_date': date_min,
            'end_date': date_max,
            'num_stores': num_stores,
            'num_families': num_families
        },
        'descriptive_statistics': desc_stats,
        'inferential_statistics': inferential_results,
        'regression_model': reg_results,
        'forecast_comparison': forecast_eval,
        'top_families': family_sales.head(10)[['sum', 'cumulative_pct']].to_dict()
    }
    
    with open(os.path.join(RESULTS_DIR, 'metrics.json'), 'w') as f:
        json.dump(all_metrics, f, indent=4)
        
    print("\n" + "="*70)
    print("ANALYSIS PIPELINE COMPLETED SUCCESSFULLY!")
    print(f"All figures and metrics saved to: {RESULTS_DIR}")
    print("="*70)

if __name__ == '__main__':
    main()
