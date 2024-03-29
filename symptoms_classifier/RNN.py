import logging
import torch
import torch.nn.functional as F
import torch.nn as nn
import torch.optim as optim
from symptoms_classifier.classifiers_utils import nn_classification_report, nn_print_perf, nn_graph_perf, prep_nn_dataset
from code_utils.plot_utils import plot_multi_lists

logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)


def test():
    from symptoms_classifier.symptoms_classifier import TextsToClassify
    from symptoms_classifier.NLP_embedding import load_embedding_model
    MAX_SEQ_LEN, tokenization_type, test_size, random_state, dropout, n_epochs, debug_mode, rnn_type = [40, None, 0.2, 0, 0.5, 50,
                                                                                              False, 'bla']
    tweets = TextsToClassify(filepath=r'C:\Users\K1774755\Downloads\phd\Tweets.csv',
                             class_col='airline_sentiment', text_col='text', binary_main_class='positive')
    df = tweets.load_data()
    sentences, y = [df.text, df.airline_sentiment.replace({'neutral': 0, 'positive': 0, 'negative': 1})]
    w2v = load_embedding_model(r'C:\Users\K1774755\PycharmProjects\toy-models\embeddings\w2v_wiki.model',
                               model_type='w2v')


def train_rnn(w2v, sentences, y, tokenization_type=None, MAX_SEQ_LEN=40, test_size=0.2, random_state=0, dropout=0.5,
              n_epochs=200, debug_mode=False, rnn_type='RNN'):
    embeddings, word2id, x_train, y_train, y_train_torch, l_train, x_test, y_test, y_test_torch, l_test = \
        prep_nn_dataset(w2v=w2v, sentences=sentences, y=y, tokenization_type=tokenization_type, test_size=test_size, MAX_SEQ_LEN=MAX_SEQ_LEN, random_state=random_state)

    class RNN(nn.Module):
        def __init__(self, embeddings, padding_idx):
            super(RNN, self).__init__()
            vocab_size = len(embeddings)
            embedding_size = len(embeddings[0])

            # Initialize embeddings
            self.embeddings = nn.Embedding(vocab_size, embedding_size, padding_idx=padding_idx)
            self.embeddings.load_state_dict({'weight': embeddings})
            self.embeddings.weight.requires_grad = False  # Disable training for the embeddings - IMPORTANT

            # Create the RNN cell
            hidden_size = 300
            if rnn_type.lower() == 'gru':
                self.rnn = nn.GRU(input_size=embedding_size, hidden_size=hidden_size, num_layers=1, dropout=dropout)
            elif rnn_type.lower() == 'lstm':
                self.rnn = nn.LSTM(input_size=embedding_size, hidden_size=hidden_size, num_layers=1, dropout=dropout)
            else:
                self.rnn = nn.RNN(input_size=embedding_size, hidden_size=hidden_size, num_layers=1, dropout=dropout)
            self.fc1 = nn.Linear(hidden_size, 2)

        def forward(self, x, lns):
            x = self.embeddings(x)  # x.shape = batch_size x sequence_length x emb_size
            # Tell RNN to ignore padding and set the batch_first to True (sequence length 1st for historical reasons)
            x = torch.nn.utils.rnn.pack_padded_sequence(x, lns, batch_first=True, enforce_sorted=False)
            x, hidden = self.rnn(x)  # run 'x' through the RNN
            x, hidden = torch.nn.utils.rnn.pad_packed_sequence(x, batch_first=True)  # Add the padding again

            # select the value at the length of that sentence (we are only interested in last output)
            row_indices = torch.arange(0, x.size(0)).long()
            x = x[row_indices, lns - 1, :]

            x = self.fc1(x)
            return x

    rnn = RNN(embeddings, padding_idx=word2id['<PAD>'])
    parameters = filter(lambda p: p.requires_grad, rnn.parameters())  # We don't want parameters that don't require a grad in the optimizer
    optimizer = optim.Adam(parameters, lr=0.001)
    criterion = nn.CrossEntropyLoss()

    losses, accs, ws, bs = [[], [], [], []]
    for epoch in range(n_epochs):
        rnn.train()
        optimizer.zero_grad()
        train_preds = rnn(x_train, l_train)  # TODO move l train to 1D CPU int64 tensor
        loss = criterion(train_preds, y_train_torch)
        loss.backward()
        optimizer.step()

        if debug_mode:  # Track the changes
            losses, accs, ws, bs = nn_graph_perf(train_preds, y_train, rnn, loss,
                                                 losses=losses, accs=accs, ws=ws, bs=bs)

        if epoch % 10 == 0:
            rnn.eval()
            outputs_train = torch.max(train_preds, 1)[1]
            outputs_test = torch.max(rnn(x_test, l_test), 1)[1]
            print("Epoch: {:4} Loss: {:.5f} ".format(epoch, loss.item()))
            nn_print_perf(train_preds=outputs_train.detach(), y_train=y_train,
                          test_preds=outputs_test.detach(), y_test=y_test)

    print('Finished Training')
    rnn.eval()
    outputs_test = torch.max(rnn(x_test, l_test), 1)[1]
    outputs_train = torch.max(rnn(x_train, l_train), 1)[1]

    if debug_mode:
        plot_multi_lists({'Bias': bs, 'Weight': ws, 'Loss': losses, 'Accuracy': accs})
    preds, df_test, df_train = nn_classification_report(y, outputs_train, y_train, outputs_test, y_test)

    return [rnn, preds, df_test, df_train]
