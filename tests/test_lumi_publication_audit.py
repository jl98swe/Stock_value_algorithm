import pandas as pd


def test_lumi_audit_does_not_use_another_issuers_same_period(tmp_path, monkeypatch):
    import src.lumi_publication_audit as audit
    # Synthetic values: two issuers share a period label, with different releases.
    folder = tmp_path / 'data/fundamentals'
    folder.mkdir(parents=True)
    publications = folder / 'report_publications.csv'
    pd.DataFrame([
        dict(ticker='LUMI.ST', report_period='2026-Q3', report_date='2026-11-04',
             published_at='2026-11-04T18:30:00-04:00'),
        dict(ticker='EXAMPLE.ST', report_period='2026-Q3', report_date='2026-10-28',
             published_at='2026-10-28T15:00:00+01:00'),
    ]).to_csv(publications,index=False)
    pd.DataFrame([
        dict(ticker=ticker,report_period='2026-Q3',eps_ttm=10,notes='',
             published_at='',effective_date='')
        for ticker in ['LUMI.ST','EXAMPLE.ST']
    ]).to_csv(folder / 'reports.csv',index=False)
    pd.DataFrame(columns=['ticker','report_period','report_date']).to_csv(
        folder / 'eps_report_date_cache.csv',index=False)
    monkeypatch.setattr(audit,'ROOT',tmp_path)
    monkeypatch.setattr(audit,'PUBLICATIONS',publications)
    audit.apply_inputs()
    reports=pd.read_csv(folder/'reports.csv')
    lumi=reports.loc[reports.ticker.eq('LUMI.ST')].iloc[0]
    assert lumi.report_date == '2026-11-04'
    assert lumi.effective_date == '2026-11-05'
    assert pd.isna(reports.loc[reports.ticker.eq('EXAMPLE.ST'),'report_date'].iloc[0])
    cache=pd.read_csv(folder/'eps_report_date_cache.csv')
    assert cache.to_dict('records') == [dict(ticker='LUMI.ST',report_period='2026-Q3',report_date='2026-11-04')]
